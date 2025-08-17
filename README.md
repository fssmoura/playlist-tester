# IPTV m3u8 updater (simple)

This repository contains a tiny script to fetch a .m3u8 URL from a webpage and update a specific channel entry in an `iptv.m3u8` file (default: `SPORT.TV2`).

Quick test (PowerShell):

powershell

If the previous script doesn't find an m3u8 because it's loaded dynamically by JS,
markdown
# IPTV m3u8 updater (moved layout)

Repository layout (moved):

- data/iptv.m3u8     (main playlist file)
- scripts/           (automation and helper scripts)
- backups/           (script-created backups)

Run updater from inside the `scripts/` directory. Scripts expect the playlist at `../data/iptv.m3u8` by default.

Examples (PowerShell) — from `scripts/`:

Dry-run capture (no write):

```powershell
& ".\.venv\Scripts\python.exe" ".\update_m3u8.py" --page "https://sportzonline.site/channels/pt/sporttv2.php" --dry-run
```

Apply update (capture → validate → write, backups to ../backups):

```powershell
& ".\.venv\Scripts\python.exe" ".\update_m3u8.py" --page "https://sportzonline.site/channels/pt/sporttv2.php" --tvg SPORT.TV2
```

Validator script (inspect an entry):

```powershell
& ".\.venv\Scripts\python.exe" ".\check_m3u_entry.py" --tvg SPORT.TV2
```

If a page loads the .m3u8 dynamically, use the Playwright helper:

```powershell
playwright install
& ".\.venv\Scripts\python.exe" ".\update_m3u8_playwright.py" --page "https://sportzonline.site/channels/pt/sporttv2.php" --tvg SPORT.TV2 --dry-run
```

Backups: scripts write timestamped backups to `backups/` by default. If you prefer a different policy, adjust the `--backup-dir` option.
```
Remove `--dry-run` to actually write the file. The script will create a timestamped `.bak` before modifying.
