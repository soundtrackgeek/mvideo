param([string]$State = (Join-Path $env:ProgramData 'mvideo'))
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$config = Get-Content -LiteralPath (Join-Path $State 'background.json') -Raw | ConvertFrom-Json
$python = $config.Python
if (!(Test-Path -LiteralPath $python -PathType Leaf)) { throw 'The installed service Python is unavailable.' }
$task = Get-ScheduledTask -TaskName 'mvideo Library' -ErrorAction Stop
$wasRunning = $task.State -eq 'Running'
$stopped = $false
$temporary = Join-Path ([IO.Path]::GetTempPath()) ('mvideo-update-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $temporary | Out-Null
try {
    $version = & $python -c 'import sys,tomllib; print(tomllib.load(open(sys.argv[1], "rb"))["project"]["version"])' (Join-Path $repo 'server\pyproject.toml')
    if ($LASTEXITCODE -ne 0) { throw 'Unable to read the new server version.' }
    # Build before stopping playback. Only the server package is installed; the
    # existing state, measurements, provider configuration and media stay in place.
    & $python -m pip wheel --no-deps --wheel-dir $temporary (Join-Path $repo 'server')
    if ($LASTEXITCODE -ne 0) { throw 'Server package build failed; the running service was not stopped.' }
    $wheels = @(Get-ChildItem -LiteralPath $temporary -Filter 'mvideo_server-*.whl')
    if ($wheels.Count -ne 1) { throw 'Expected exactly one built mvideo server wheel.' }
    if ($wasRunning) {
        Stop-ScheduledTask -TaskName 'mvideo Library'
        $stopped = $true
        for ($attempt = 0; $attempt -lt 30; $attempt++) {
            if ((Get-ScheduledTask -TaskName 'mvideo Library').State -ne 'Running') { break }
            Start-Sleep -Seconds 1
        }
        if ((Get-ScheduledTask -TaskName 'mvideo Library').State -eq 'Running') { throw 'The service did not stop; package installation was cancelled.' }
    }
    & $python -m pip install --no-index --no-deps --upgrade $wheels[0].FullName
    if ($LASTEXITCODE -ne 0) { throw 'Server package installation failed. Check the pip output above.' }
} finally {
    if ($stopped) { Start-ScheduledTask -TaskName 'mvideo Library' }
    Remove-Item -LiteralPath $temporary -Recurse -Force
}
if ($wasRunning) {
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        try {
            $health = Invoke-RestMethod 'http://127.0.0.1:8765/health' -TimeoutSec 2
            if ($health.service -eq 'mvideo' -and $health.version -eq $version) {
                Write-Output "mvideo $version is running. Existing measurements and library state were retained."
                exit 0
            }
        } catch { }
        Start-Sleep -Seconds 1
    }
    throw "Installed mvideo $version, but the service health check did not confirm that version. Check Task Scheduler and $State\service.log."
}
Write-Output "Installed mvideo $version. The task was stopped before the update and remains stopped. Start 'mvideo Library' in Task Scheduler when ready."
