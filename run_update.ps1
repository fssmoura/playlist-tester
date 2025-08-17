param(
    [string]$page,
    [string]$tvg = "SPORT.TV2",
    [switch]$DryRun
)

$scriptDir = Join-Path $PSScriptRoot 'scripts'
$python = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$cmd = "& `"$python`" `"$scriptDir\update_m3u8.py`" --page `"$page`" --tvg $tvg"
if ($DryRun) { $cmd += ' --dry-run' }
Invoke-Expression $cmd
