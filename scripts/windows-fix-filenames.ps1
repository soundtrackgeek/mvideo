param(
    [string]$Library = '',
    [string]$State = '',
    [string]$PythonPath = '',
    [string]$Plan = '',
    [switch]$Apply
)
$ErrorActionPreference = 'Stop'
$python = & (Join-Path $PSScriptRoot 'windows-python.ps1') -Library $Library -State $State -PythonPath $PythonPath
$cliArgs = @('-m', 'mvideo.cli', 'fix-filenames')
if ($Plan) { $cliArgs += @('--plan', $Plan) }
if ($Apply) { $cliArgs += '--apply' }
& $python @cliArgs
exit $LASTEXITCODE
