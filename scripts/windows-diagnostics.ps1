$ErrorActionPreference = 'Stop'
Start-Transcript -Path (Join-Path (Split-Path $PSScriptRoot -Parent) 'diagnostics.txt') -Force | Out-Null
# Read-only. No account values, tokens, full environment or provider keys are printed.
Write-Output "Windows identity: $([System.Security.Principal.WindowsIdentity]::GetCurrent().Name)"
Write-Output "Media root available: $(Test-Path -LiteralPath 'L:\MusicVideos')"
Get-Command python,py,ffmpeg,ffprobe,tailscale -ErrorAction SilentlyContinue | Select-Object Name,Source
Get-Service | Where-Object { $_.Name -match 'mvideo|tailscale|sshd' } | Select-Object Name,Status
& tailscale serve status
Get-NetTCPConnection -State Listen | Where-Object { $_.LocalPort -in 443,8443,8765 } | Select-Object LocalAddress,LocalPort,OwningProcess
Stop-Transcript | Out-Null
