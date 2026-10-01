param(
    [string]$Library = '',
    [string]$State = '',
    [string]$PythonPath = '',
    [switch]$Force,
    [ValidateRange(0, 2147483647)][int]$Limit = 0,
    [ValidateRange(1, 2147483647)][int]$TimeoutSeconds = 1800,
    [switch]$Status
)
$ErrorActionPreference = 'Stop'
$python = & (Join-Path $PSScriptRoot 'windows-python.ps1') -Library $Library -State $State -PythonPath $PythonPath
$cliArgs = @('-m', 'mvideo.cli', 'measure-loudness', '--timeout', "$TimeoutSeconds")
if ($Force) { $cliArgs += '--force' }
if ($Limit -gt 0) { $cliArgs += @('--limit', "$Limit") }
if ($Status) { $cliArgs += '--status' }
& $python @cliArgs
exit $LASTEXITCODE
