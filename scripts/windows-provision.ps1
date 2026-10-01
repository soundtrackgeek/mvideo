param([switch]$Prepare, [switch]$Import)
$ErrorActionPreference = 'Stop'
# One-time encrypted transfer from the owner's Mac. Provider values never enter command arguments or logs.
$repo = Split-Path $PSScriptRoot -Parent
$state = Join-Path $env:LOCALAPPDATA 'mvideo'
New-Item -ItemType Directory -Force -Path $state | Out-Null
$privateFile = Join-Path $state 'provision-private.dpapi'
$rsa = [System.Security.Cryptography.RSA]::Create(2048)
try {
    if ($Prepare) {
        if (Test-Path $privateFile) { throw 'A transfer is already prepared.' }
        $rsa.ToXmlString($true) | ConvertTo-SecureString -AsPlainText -Force | ConvertFrom-SecureString | Set-Content $privateFile
        $rsa.ToXmlString($false) | Set-Content (Join-Path $repo 'provision-public.xml')
        Write-Output 'Public encryption key ready. Private key is protected by current-user DPAPI.'
    } elseif ($Import) {
        $secure = (Get-Content $privateFile -Raw).Trim() | ConvertTo-SecureString
        $rsa.FromXmlString([System.Net.NetworkCredential]::new('', $secure).Password)
        $payload = Join-Path $repo 'providers.encrypted'
        $json = [Text.Encoding]::UTF8.GetString($rsa.Decrypt([IO.File]::ReadAllBytes($payload), [System.Security.Cryptography.RSAEncryptionPadding]::OaepSHA1))
        $data = $json | ConvertFrom-Json
        if (!$data.LAST_FM -or !$data.FANART_TV) { throw 'Both provider keys are required.' }
        $json | ConvertTo-SecureString -AsPlainText -Force | ConvertFrom-SecureString | Set-Content (Join-Path $state 'providers.dpapi')
        Remove-Item $privateFile, $payload, (Join-Path $repo 'provision-public.xml')
        Write-Output 'Provider keys saved with current-user DPAPI. One-time transfer files removed.'
    } else { throw 'Choose -Prepare or -Import.' }
} finally { $rsa.Dispose() }
