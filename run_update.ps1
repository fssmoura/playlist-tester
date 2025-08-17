param(
    [string]$page,
    [string]$tvg = "SPORT.TV2",
    [switch]$Apply
)

$scriptDir = Join-Path $PSScriptRoot 'scripts'
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'

# Use Playwright helper by default because many pages generate m3u8 tokens via JS.
$script = Join-Path $scriptDir 'update_m3u8_playwright.py'
$cmd = "& `"$python`" `"$script`" --page `"$page`" --file `"$(Join-Path $PSScriptRoot 'data\iptv.m3u8')`" --tvg $tvg --dry-run"

# Default behavior is dry-run. Use -Apply to actually write the file.
if ($Apply) {
    # call without --dry-run to apply. We intentionally do not pass a backup-dir so
    # the updater will not create backups by default.
    $cmd = "& `"$python`" `"$script`" --page `"$page`" --file `"$(Join-Path $PSScriptRoot 'data\iptv.m3u8')`" --tvg $tvg"
}

Invoke-Expression $cmd
