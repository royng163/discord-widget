# Discord WakaTime Widget

A Discord profile widget: a WakaTime activity card that updates itself every 30 minutes
via GitHub Actions.

## How It Works

`sync_widget.py` (Python standard library only):

1. Fetches weekly stats from WakaTime (`stats/last_7_days`) for weekly coded time, AI
   coding, token usage, cost, and daily average.
2. Reuses two all-time figures (Total Time Coded, Total Line Written) already rendered as
   [waka-readme-stats](https://github.com/anmol098/waka-readme-stats) badges in a GitHub
   profile README - no GitHub token or line-count job needed.
3. Builds the Discord widget `data.dynamic` payload, including the subtitles and the
   `profile.gif` image (committed here and served via raw GitHub).
4. PATCHes it onto a Discord application profile.

The workflow runs on cron `*/30 * * * *`.

## Configuration

Secrets (`Settings -> Secrets and variables -> Actions`):

| Secret | Purpose |
| --- | --- |
| `WAKATIME_API_KEY` | WakaTime API key (Basic Auth) |
| `DISCORD_APPLICATION_ID` | Discord application ID |
| `DISCORD_USER_ID` | Discord user ID to update |
| `DISCORD_BOT_TOKEN` | Discord bot token |

Repository variables (optional personalization, all default to blank):

| Variable | Purpose |
| --- | --- |
| `PROFILE_README_URL` | Raw URL of a profile README with waka-readme-stats badges; blank skips the two all-time stats |
| `PROFILE_IMAGE_URL` | Widget image; defaults to `profile.gif` in this repo |
| `TITLE` | Profile title (display name shown on the widget) |
| `SUBTITLE_1`, `SUBTITLE_2`, `SUBTITLE_3` | Profile subtitle lines |

Run `python3 sync_widget.py --selftest` to check the badge parser.

## Credits

Based on the original [discord_wakatime_widget by tickcount](https://github.com/tickcount/discord_wakatime_widget).
All-time stats come from [waka-readme-stats](https://github.com/anmol098/waka-readme-stats).

## License

[MIT](LICENSE).
