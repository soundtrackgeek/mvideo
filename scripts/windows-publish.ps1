$ErrorActionPreference = 'Stop'
$health = Invoke-RestMethod 'http://127.0.0.1:8765/health'
if ($health.service -ne 'mvideo') { throw 'mvideo is not running on its loopback port.' }
# Adds only mvideo's private HTTPS port. Never reset Serve or enable Funnel.
& tailscale serve --bg --https=8443 http://127.0.0.1:8765
if ($LASTEXITCODE -ne 0) { throw 'Unable to configure the private HTTPS endpoint.' }
& tailscale serve status
