$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$LogDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

Start-Process -FilePath "node" `
  -ArgumentList "src\bridge_server.js" `
  -WorkingDirectory $Root `
  -RedirectStandardOutput (Join-Path $LogDir "bridge.log") `
  -RedirectStandardError (Join-Path $LogDir "bridge.err.log") `
  -WindowStyle Hidden

Start-Process -FilePath "node" `
  -ArgumentList "src\server.js" `
  -WorkingDirectory $Root `
  -RedirectStandardOutput (Join-Path $LogDir "server.log") `
  -RedirectStandardError (Join-Path $LogDir "server.err.log") `
  -WindowStyle Hidden

Write-Host "Bridge starting..."
Write-Host "  Server: http://127.0.0.1:8787/api/health"
Write-Host "  Bridge: http://127.0.0.1:8787/api/gateway/health"
Write-Host "  Panel:  http://127.0.0.1:8787/"
