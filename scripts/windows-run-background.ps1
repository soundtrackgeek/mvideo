param([string]$State = (Join-Path $env:ProgramData 'mvideo'))
$ErrorActionPreference = 'Stop'
$config = Get-Content (Join-Path $State 'background.json') -Raw | ConvertFrom-Json
$env:MVIDEO_STATE = $State
$env:MVIDEO_LIBRARY = $config.Library
$env:MVIDEO_FFMPEG = $config.FFmpeg
$env:MVIDEO_FFPROBE = $config.FFprobe
$env:PYTHONDONTWRITEBYTECODE = '1'
# A local drive may become ready shortly after Task Scheduler starts.
for ($attempt = 0; $attempt -lt 60 -and !(Test-Path -LiteralPath $config.Library); $attempt++) { Start-Sleep -Seconds 5 }
if (!(Test-Path -LiteralPath $config.Library)) { throw 'Library drive is unavailable.' }
Add-Type -AssemblyName System.Security
$secretFile = Join-Path $State 'providers.machine.dpapi'
if (Test-Path $secretFile) {
    $bytes = [Security.Cryptography.ProtectedData]::Unprotect([IO.File]::ReadAllBytes($secretFile), $null, [Security.Cryptography.DataProtectionScope]::LocalMachine)
    $providers = [Text.Encoding]::UTF8.GetString($bytes) | ConvertFrom-Json
    foreach ($name in 'LAST_FM','FANART_TV') { [Environment]::SetEnvironmentVariable($name, $providers.$name, 'Process') }
    [Array]::Clear($bytes, 0, $bytes.Length)
}
if (!(Test-Path -LiteralPath $config.Python -PathType Leaf)) { throw 'The configured service Python is unavailable.' }
Set-Location $config.Repository
$log = Join-Path $State 'service.log'
if (Test-Path $log) { Move-Item $log ($log + '.previous') -Force }
$serviceExitCode = 1
$LASTEXITCODE = $null
$previousErrorActionPreference = $ErrorActionPreference
try {
    # Windows PowerShell 5.1 turns redirected native stderr into PowerShell errors.
    # A Python warning must be logged without terminating the running service.
    $ErrorActionPreference = 'Continue'
    & $config.Python -m mvideo.cli serve --port 8765 --scan-interval 1800 *> $log
    if ($null -ne $LASTEXITCODE) { $serviceExitCode = $LASTEXITCODE }
} finally {
    $ErrorActionPreference = $previousErrorActionPreference
}
exit $serviceExitCode
