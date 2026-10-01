$ErrorActionPreference = 'Stop'
$state = Join-Path $env:LOCALAPPDATA 'mvideo'
New-Item -ItemType Directory -Force -Path $state | Out-Null
$values = @{}
foreach ($name in 'LAST_FM','FANART_TV') {
    $value = Read-Host "Enter $name (server only)" -AsSecureString
    $values[$name] = [System.Net.NetworkCredential]::new('', $value).Password
}
# Current Windows account DPAPI. No plaintext secret file and no console echo.
$json = $values | ConvertTo-Json -Compress
ConvertTo-SecureString $json -AsPlainText -Force | ConvertFrom-SecureString | Set-Content -LiteralPath (Join-Path $state 'providers.dpapi')
$values.Clear(); $json = $null
Write-Output 'Provider keys saved for this Windows account. LAST_FM_SECRET is not needed for artist.getInfo.'
