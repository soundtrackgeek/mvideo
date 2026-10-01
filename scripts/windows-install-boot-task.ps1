#Requires -RunAsAdministrator
param([string]$Library = 'L:\MusicVideos')
$ErrorActionPreference = 'Stop'
$repo = Split-Path $PSScriptRoot -Parent
$state = Join-Path $env:ProgramData 'mvideo'
$oldState = Join-Path $env:LOCALAPPDATA 'mvideo'
$python = Join-Path $repo '.venv\Scripts\python.exe'
$launcher = Join-Path $PSScriptRoot 'windows-run-background.ps1'
$name = 'mvideo Library'
if (!(Test-Path $python) -or !(Test-Path -LiteralPath $Library)) { throw 'Run Windows setup first and check the local library drive.' }
$existing = Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
if ($existing -and $existing.Actions.Arguments -notlike "*$PSScriptRoot*") { throw 'A different task owns this name.' }
$prior = if ($existing) { Export-ScheduledTask -TaskName $name } else { $null }
$owner = [Security.Principal.WindowsIdentity]::GetCurrent().User
$localService = [Security.Principal.SecurityIdentifier]::new('S-1-5-19')
$administrators = [Security.Principal.SecurityIdentifier]::new('S-1-5-32-544')
$system = [Security.Principal.SecurityIdentifier]::new('S-1-5-18')
function Protect-Directory([string]$Path, [string]$ServiceRights) {
    New-Item -ItemType Directory -Force -Path $Path | Out-Null
    $acl = [Security.AccessControl.DirectorySecurity]::new()
    $acl.SetAccessRuleProtection($true, $false)
    $acl.SetOwner($owner)
    foreach ($identity in @($owner, $administrators, $system)) {
        $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($identity,'FullControl','ContainerInherit,ObjectInherit','None','Allow'))
    }
    $acl.AddAccessRule([Security.AccessControl.FileSystemAccessRule]::new($localService,$ServiceRights,'ContainerInherit,ObjectInherit','None','Allow'))
    Set-Acl -LiteralPath $Path -AclObject $acl
}
# Machine DPAPI requires these ACLs: no other local account can read the encrypted keys.
Protect-Directory $state 'Modify'
Protect-Directory $repo 'ReadAndExecute'
if ($prior) { $prior | Set-Content (Join-Path $state 'previous-task.xml') }
@{ Repository=$repo; Python=$python; Library=$Library; FFmpeg=(Get-Command ffmpeg).Source; FFprobe=(Get-Command ffprobe).Source } |
    ConvertTo-Json | Set-Content (Join-Path $state 'background.json')
$sourceSecrets = Join-Path $oldState 'providers.dpapi'
if (Test-Path $sourceSecrets) {
    Add-Type -AssemblyName System.Security
    $secure = (Get-Content $sourceSecrets -Raw).Trim() | ConvertTo-SecureString
    $plain = [System.Net.NetworkCredential]::new('', $secure).Password
    $bytes = [Text.Encoding]::UTF8.GetBytes($plain)
    [IO.File]::WriteAllBytes((Join-Path $state 'providers.machine.dpapi'), [Security.Cryptography.ProtectedData]::Protect($bytes, $null, [Security.Cryptography.DataProtectionScope]::LocalMachine))
    [Array]::Clear($bytes, 0, $bytes.Length)
    $plain = $null
}
try {
    if ($existing) { Stop-ScheduledTask -TaskName $name; Start-Sleep -Seconds 3 }
    if (!(Test-Path (Join-Path $state 'library.sqlite3')) -and (Test-Path (Join-Path $oldState 'library.sqlite3'))) {
        & $python -c 'import sqlite3,sys; a=sqlite3.connect(sys.argv[1]); b=sqlite3.connect(sys.argv[2]); a.backup(b); b.close(); a.close()' (Join-Path $oldState 'library.sqlite3') (Join-Path $state 'library.sqlite3')
        if ($LASTEXITCODE -ne 0) { throw 'Unable to migrate the existing library database.' }
    }
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -NonInteractive -WindowStyle Hidden -File `"$launcher`"" -WorkingDirectory $repo
    $principal = New-ScheduledTaskPrincipal -UserId 'S-1-5-19' -LogonType ServiceAccount -RunLevel Limited
    $trigger = New-ScheduledTaskTrigger -AtStartup
    $trigger.Delay = 'PT30S'
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 10 -RestartInterval (New-TimeSpan -Minutes 1) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew
    Register-ScheduledTask -TaskName $name -Action $action -Principal $principal -Trigger $trigger -Settings $settings -Description 'mvideo library starts at Windows boot without an interactive login. Private loopback only.' -Force | Out-Null
    Start-ScheduledTask -TaskName $name
    $healthy = $false
    for ($attempt=0; $attempt -lt 15; $attempt++) {
        Start-Sleep -Seconds 2
        try { $health = Invoke-RestMethod 'http://127.0.0.1:8765/health'; if ($health.service -eq 'mvideo') { $healthy=$true; break } } catch { }
    }
    if (!$healthy) { throw 'Background service health check failed; restoring the previous task.' }
    Write-Output 'mvideo now runs as Local Service and starts 30 seconds after Windows boot, without a login.'
    $health | ConvertTo-Json
    Get-ScheduledTask -TaskName $name | Select-Object TaskName,State,@{Name='Account';Expression={$_.Principal.UserId}},@{Name='Trigger';Expression={$_.Triggers.CimClass.CimClassName}}
} catch {
    if ($prior) {
        Stop-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
        Register-ScheduledTask -TaskName $name -Xml $prior -Force | Out-Null
        Start-ScheduledTask -TaskName $name
    }
    throw
}
