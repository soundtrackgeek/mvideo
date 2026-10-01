param([string]$Library = 'L:\MusicVideos', [int]$Port = 8765, [switch]$Pair, [switch]$Scan)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$env:MVIDEO_LIBRARY = $Library
$env:MVIDEO_STATE = Join-Path $env:LOCALAPPDATA 'mvideo'
if (!(Test-Path -LiteralPath $Library)) { throw 'Library is unavailable in this Windows account.' }
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (!(Test-Path $python)) {
    & py -3.12 -m venv (Join-Path $repo '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12, then rerun.' }
}
& $python -m pip install -e (Join-Path $repo 'server')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
foreach ($tool in 'ffmpeg','ffprobe') { if (!(Get-Command $tool -ErrorAction SilentlyContinue)) { throw "Install FFmpeg including $tool and add it to PATH." } }
$secretFile = Join-Path $env:MVIDEO_STATE 'providers.dpapi'
if (Test-Path $secretFile) {
    $encrypted = Get-Content -LiteralPath $secretFile -Raw | ConvertTo-SecureString
    $plain = [System.Net.NetworkCredential]::new('', $encrypted).Password | ConvertFrom-Json
    foreach ($name in 'LAST_FM','FANART_TV') { [Environment]::SetEnvironmentVariable($name, $plain.$name, 'Process') }
}
if ($Pair) { & $python -m mvideo.cli pair; exit $LASTEXITCODE }
if ($Scan) { & $python -m mvideo.cli scan; exit $LASTEXITCODE }
# Intentionally loopback-only. Configure a separate private Tailscale Serve HTTPS port after diagnostics.
& $python -m mvideo.cli serve --port $Port
