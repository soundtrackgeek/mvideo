param([string]$Library = 'L:\MusicVideos', [int]$Port = 8765, [switch]$Pair, [switch]$Scan, [string]$State = '')
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$env:MVIDEO_LIBRARY = $Library
if (!$State) {
    $task = Get-ScheduledTask -TaskName 'mvideo Library' -ErrorAction SilentlyContinue
    $State = if ($task.Actions.Arguments -like '*windows-run-background.ps1*') { Join-Path $env:ProgramData 'mvideo' } else { Join-Path $env:LOCALAPPDATA 'mvideo' }
}
$env:MVIDEO_STATE = $State
if (!(Test-Path -LiteralPath $Library)) { throw 'Library is unavailable in this Windows account.' }
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (!(Test-Path $python)) {
    & python -c 'import sys; sys.exit(0 if sys.version_info >= (3,12) else 1)'
    if ($LASTEXITCODE -ne 0) { throw 'Install Python 3.12 or later, then rerun.' }
    & python -m venv (Join-Path $repo '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Unable to create the Python environment.' }
}
if (!(Test-Path (Join-Path $repo '.venv\Lib\site-packages\mvideo_server-*.dist-info'))) {
    & $python -m pip install -r (Join-Path $repo 'server\requirements.lock')
    if ($LASTEXITCODE -ne 0) { throw 'Pinned dependency installation failed.' }
    & $python -m pip install --no-deps -e (Join-Path $repo 'server')
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
}
foreach ($tool in 'ffmpeg','ffprobe') { if (!(Get-Command $tool -ErrorAction SilentlyContinue)) { throw "Install FFmpeg including $tool and add it to PATH." } }
$secretFile = Join-Path $env:MVIDEO_STATE 'providers.dpapi'
if (Test-Path $secretFile) {
    $encrypted = (Get-Content -LiteralPath $secretFile -Raw).Trim() | ConvertTo-SecureString
    $plain = [System.Net.NetworkCredential]::new('', $encrypted).Password | ConvertFrom-Json
    foreach ($name in 'LAST_FM','FANART_TV') { [Environment]::SetEnvironmentVariable($name, $plain.$name, 'Process') }
}
if ($Pair) { & $python -m mvideo.cli pair; exit $LASTEXITCODE }
if ($Scan) { & $python -m mvideo.cli scan; exit $LASTEXITCODE }
# Intentionally loopback-only. Configure a separate private Tailscale Serve HTTPS port after diagnostics.
& $python -m mvideo.cli serve --port $Port --scan-interval 1800
