param(
    [string]$Library = '',
    [string]$State = '',
    [switch]$Force,
    [ValidateRange(0, 2147483647)][int]$Limit = 0,
    [ValidateRange(1, 2147483647)][int]$TimeoutSeconds = 1800,
    [switch]$Status
)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
if (!$State) {
    if ($env:MVIDEO_STATE) { $State = $env:MVIDEO_STATE }
    elseif (Test-Path (Join-Path $env:ProgramData 'mvideo\background.json')) { $State = Join-Path $env:ProgramData 'mvideo' }
    else { $State = Join-Path $env:LOCALAPPDATA 'mvideo' }
}
$configFile = Join-Path $State 'background.json'
$config = if (Test-Path -LiteralPath $configFile) { Get-Content -LiteralPath $configFile -Raw | ConvertFrom-Json } else { $null }
if (!$Library) {
    $Library = if ($config) { $config.Library } elseif ($env:MVIDEO_LIBRARY) { $env:MVIDEO_LIBRARY } else { 'L:\MusicVideos' }
}
$env:MVIDEO_STATE = $State
$env:MVIDEO_LIBRARY = $Library
if ($config) {
    $env:MVIDEO_FFMPEG = $config.FFmpeg
    $env:MVIDEO_FFPROBE = $config.FFprobe
}
$python = Join-Path $repo '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $python)) { throw 'Run scripts/windows-start.ps1 -Scan once to install and index this library.' }
# Use the source beside this launcher even if the installed package is older.
$env:PYTHONPATH = (Join-Path $repo 'server') + [IO.Path]::PathSeparator + $env:PYTHONPATH
$env:PYTHONUTF8 = '1'
$cliArgs = @('-m', 'mvideo.cli', 'measure-loudness', '--timeout', "$TimeoutSeconds")
if ($Force) { $cliArgs += '--force' }
if ($Limit -gt 0) { $cliArgs += @('--limit', "$Limit") }
if ($Status) { $cliArgs += '--status' }
& $python @cliArgs
exit $LASTEXITCODE
