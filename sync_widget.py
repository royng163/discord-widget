import base64
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import unquote


WAKATIME_STATS_URL = "https://api.wakatime.com/api/v1/users/current/stats/last_7_days"
DISCORD_PROFILE_URL = (
    "https://discord.com/api/v9/applications/{application_id}"
    "/users/{user_id}/identities/0/profile"
)
REQUEST_TIMEOUT_SECONDS = 30

IMAGE_FILENAME = "profile.gif"


def default_image_url():
    repo = os.environ.get("GITHUB_REPOSITORY")
    branch = os.environ.get("GITHUB_REF_NAME", "main")
    if repo:
        return f"https://raw.githubusercontent.com/{repo}/{branch}/{IMAGE_FILENAME}"
    return ""


# PROFILE_README_URL: raw profile README with waka-readme-stats badges (all-time stats).
PROFILE_README_URL = os.environ.get("PROFILE_README_URL", "")
PROFILE_IMAGE_URL = os.environ.get("PROFILE_IMAGE_URL") or default_image_url()
TITLE = os.environ.get("TITLE", "")
SUBTITLE_1 = os.environ.get("SUBTITLE_1", "")
SUBTITLE_2 = os.environ.get("SUBTITLE_2", "")
SUBTITLE_3 = os.environ.get("SUBTITLE_3", "")


def log_step(message):
    print(f"[step] {message}")


def print_json(title, payload):
    print(f"[json] {title}:")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def is_debug_wakatime_json_enabled():
    return os.environ.get("DEBUG_WAKATIME_JSON") == "1"


def require_env(name):
    log_step(f"Reading {name} from environment")
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def compact_number(value):
    value = int(value or 0)
    for suffix, threshold in (("B", 1_000_000_000), ("M", 1_000_000), ("K", 1_000)):
        if value >= threshold:
            number = f"{value / threshold:.1f}".rstrip("0").rstrip(".")
            return f"{number}{suffix}"
    return str(value)


def get_number(data, name):
    value = data.get(name, 0)
    return value if isinstance(value, (int, float)) else 0


# WakaTime prices each model name by a default version (wakatime.com/faq#ai-model-cost).
# static map, update when WakaTime changes its default versions.
AI_MODEL_VERSIONS = {
    "Opus": "4.8",
    "Sonnet": "4.6",
    "Haiku": "4.5",
    "GPT": "5.6",
    "Gemini": "3.1-pro",
    "Grok": "4.5",
    "Qwen": "3.7-max",
}


def model_display_name(name):
    version = AI_MODEL_VERSIONS.get(name)
    return f"{name} {version}" if version else name


def best_ai_agent_by_cost(stats):
    agents = stats.get("ai_model_breakdown") or []
    if not agents:
        return "Unknown"

    agent = max(agents, key=lambda item: get_number(item, "cost"))
    return model_display_name(agent.get("name", "Unknown"))


_MAGNITUDE = {"thousand": "K", "million": "M", "billion": "B"}


def parse_profile_badges(readme_text):
    """Pull all-time coding time and total lines from waka-readme-stats shields.io badges."""
    code_time = "∞ Hours"
    total_lines = "∞ Lines"

    match = re.search(r"Code%20Time-([^-]+)-", readme_text)
    if match:
        code_time = unquote(match.group(1)).strip()

    match = re.search(r"Written-([^-]+)-blue", readme_text)
    if match:
        text = unquote(match.group(1)).strip()
        num = re.search(r"(\d[\d.]*)\s*(thousand|million|billion)?", text)
        if num:
            suffix = _MAGNITUDE.get(num.group(2), "")
            total_lines = f"{num.group(1)}{suffix} Lines"

    return code_time, total_lines


def request_text(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Discord WakaTime Widget"})
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return response.read().decode("utf-8")


def fetch_profile_badges():
    if not PROFILE_README_URL:
        log_step("No PROFILE_README_URL set, using placeholders for all-time stats")
        return parse_profile_badges("")
    log_step("Fetching profile README for all-time stats")
    try:
        return parse_profile_badges(request_text(PROFILE_README_URL))
    except (urllib.error.URLError, OSError) as error:
        log_step(f"Profile README fetch failed, using placeholders: {error}")
        return parse_profile_badges("")


def request_json(url, headers, method="GET", body=None):
    request = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method=method,
    )

    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            text = response.read().decode("utf-8")
            if not text:
                return response.status, {}
            return response.status, json.loads(text)
    except urllib.error.HTTPError as error:
        text = error.read().decode("utf-8")
        if not text:
            return error.code, {}
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = {"error": text}
        return error.code, payload


def fetch_wakatime_stats(api_key):
    log_step("Preparing WakaTime Basic Auth header")
    basic = base64.b64encode(api_key.encode("utf-8")).decode("ascii")
    headers = {
        "Authorization": f"Basic {basic}",
        "Accept": "application/json",
        "User-Agent": "Discord WakaTime Widget",
    }

    for attempt in range(1, 6):
        log_step(f"Requesting WakaTime stats, attempt {attempt}/5")
        status, payload = request_json(WAKATIME_STATS_URL, headers)
        log_step(f"WakaTime response status: HTTP {status}")
        if is_debug_wakatime_json_enabled():
            print_json("WakaTime response", payload)

        data = payload.get("data") or {}

        if status == 200 and data.get("status") == "ok":
            log_step("WakaTime stats are ready")
            return data

        if status == 202 or data.get("status") == "pending_update":
            timeout = int(data.get("timeout") or 15)
            log_step(f"WakaTime stats are pending, waiting {min(timeout, 60)} seconds")
            time.sleep(min(timeout, 60))
            continue

        raise RuntimeError(f"WakaTime API error {status}: {json.dumps(payload)}")

    raise RuntimeError("WakaTime stats are still pending_update after retries")


def build_discord_payload(stats, code_time, total_lines):
    log_step("Building Discord widget payload from WakaTime stats")

    daily_average = f"Daily Average: {stats.get('human_readable_daily_average', '')}"
    tokens = (
        f"{compact_number(get_number(stats, 'ai_input_tokens'))} in "
        f"\u00b7 {compact_number(get_number(stats, 'ai_output_tokens'))} out"
    )

    def text(name, value):
        return {"type": 1, "name": name, "value": value}

    def image(name, url):
        return {"type": 3, "name": name, "value": {"url": url}}

    return {
        "data": {
            "dynamic": [
                text("stat_1_name", code_time),
                text("stat_1_value", "Total Time Coded"),
                text("stat_2_name", stats.get("human_readable_total", "")),
                text("stat_2_value", "Weekly Coded"),
                text("stat_3_name", total_lines),
                text("stat_3_value", "Total Lines of Code"),
                text("stat_4_name", best_ai_agent_by_cost(stats)),
                text("stat_4_value", "Most Used AI"),
                text("stat_5_name", tokens),
                text("stat_5_value", "Weekly Tokens"),
                text("stat_6_name", f"${get_number(stats, 'ai_model_total_cost'):,.0f}"),
                text("stat_6_value", "Weekly Est. Cost"),
                text("stat_mini_profile", daily_average),
                text("stat_activity_accessory", daily_average),
                text("subtitle_1", SUBTITLE_1),
                text("subtitle_2", SUBTITLE_2),
                text("subtitle_3", SUBTITLE_3),
                image("image_top", PROFILE_IMAGE_URL),
                image("image_mini", PROFILE_IMAGE_URL),
                text("title", TITLE),
            ]
        }
    }


def patch_discord_profile(application_id, user_id, bot_token, payload):
    log_step("Preparing Discord profile PATCH request")
    url = DISCORD_PROFILE_URL.format(application_id=application_id, user_id=user_id)
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    headers = {
        "Authorization": f"Bot {bot_token}",
        "Content-Type": "application/json",
        "User-Agent": "DiscordBot (https://github.com/discord/discord-api-docs, 1.0.0)",
    }

    log_step("Sending Discord profile PATCH request")
    status, response = request_json(url, headers, method="PATCH", body=body)
    log_step(f"Discord response status: HTTP {status}")
    print_json("Discord response", response)

    if status < 200 or status >= 300:
        raise RuntimeError(f"Discord API error {status}: {json.dumps(response)}")

    return status, response


def demo():
    badge = (
        "![Code Time](http://img.shields.io/badge/Code%20Time-1%2C375%20hrs-blue?style=flat)\n"
        "![Lines of code](https://img.shields.io/badge/From%20Hello%20World%20I%27ve%20Written-2.03%20million%20lines%20of%20code-blue?style=flat)"
    )
    assert parse_profile_badges(badge) == ("1,375 hrs", "2.03M Lines"), parse_profile_badges(badge)
    assert parse_profile_badges("") == ("∞ Hours", "∞ Lines")
    print("selftest ok")


def main():
    log_step("Starting Discord WakaTime widget sync")
    stats = fetch_wakatime_stats(require_env("WAKATIME_API_KEY"))
    code_time, total_lines = fetch_profile_badges()
    payload = build_discord_payload(stats, code_time, total_lines)

    print_json("Discord payload", payload)

    status, _ = patch_discord_profile(
        require_env("DISCORD_APPLICATION_ID"),
        require_env("DISCORD_USER_ID"),
        require_env("DISCORD_BOT_TOKEN"),
        payload,
    )
    log_step(f"Discord profile updated: HTTP {status}")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        demo()
        sys.exit(0)
    try:
        main()
    except Exception as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
