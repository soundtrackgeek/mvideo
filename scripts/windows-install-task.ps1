param([switch]$Restart)
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$name = 'mvideo Library'
$launcher = Join-Path $PSScriptRoot 'windows-start.ps1'
$existing = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
if ($existing -and $existing.Actions.Arguments -notlike "*$launcher*") {
    throw 'A different task already owns this name; no changes made.'
}
if ($existing -and $Restart) { Stop-ScheduledTask -TaskName $name; Start-Sleep -Seconds 2 }
$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -WindowStyle Hidden -File `"$launcher`"" -WorkingDirectory $repo
$identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal = New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
$trigger = New-ScheduledTaskTrigger -AtLogOn -User $identity
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName $name -Action $action -Principal $principal -Trigger $trigger -Settings $settings -Description 'mvideo personal video library; loopback only; current user DPAPI secrets.' -Force | Out-Null
Start-ScheduledTask -TaskName $name
Start-Sleep -Seconds 3
Invoke-RestMethod 'http://127.0.0.1:8765/health' | ConvertTo-Json
Get-ScheduledTask -TaskName $name | Select-Object TaskName,State
