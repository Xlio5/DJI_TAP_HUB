$ports = @(8787, 49620, 49621, 49622, 49623, 49624, 49625, 49626, 49627, 49628, 49629)

foreach ($port in $ports) {
  Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique |
    ForEach-Object {
      Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue
    }
}

Write-Host "Bridge stopped."
