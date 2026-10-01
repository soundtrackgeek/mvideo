$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$task = Get-ScheduledTask -TaskName 'mvideo Library' -ErrorAction SilentlyContinue
$env:MVIDEO_STATE = if ($task.Actions.Arguments -like '*windows-run-background.ps1*') { Join-Path $env:ProgramData 'mvideo' } else { Join-Path $env:LOCALAPPDATA 'mvideo' }
$env:MVIDEO_LIBRARY = 'L:\MusicVideos'
$python = Join-Path $repo '.venv\Scripts\python.exe'
Invoke-RestMethod 'http://127.0.0.1:8765/health' | ConvertTo-Json | Set-Content (Join-Path $repo 'health.json')
& $python -m mvideo.cli report | Set-Content (Join-Path $repo 'library-report.json')
# Short-lived one-use handoff for integration verification. Consume immediately, then remove this file.
& $python -m mvideo.cli pair | Set-Content (Join-Path $repo 'pairing-code.txt')
Write-Output 'Health, catalog report and one-time verification code ready.'
$task | Select-Object TaskName,State,@{Name='Account';Expression={$_.Principal.UserId}},@{Name='Trigger';Expression={$_.Triggers.CimClass.CimClassName}} | ConvertTo-Json | Set-Content (Join-Path $repo 'startup-report.json')
