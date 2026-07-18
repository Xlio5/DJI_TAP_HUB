$p = New-Object System.IO.Ports.SerialPort "COM10", 115200, None, 8, One
$p.ReadTimeout = 500
$p.Open()
Write-Host "Connected"

function _rr($ms) {
    $end = (Get-Date).AddMilliseconds($ms)
    $buf = New-Object byte[] 4096
    while ((Get-Date) -lt $end) {
        try { $n = $p.Read($buf, 0, $buf.Length) } catch { break }
        if ($n -gt 0) { Write-Host -NoNewline ([System.Text.Encoding]::ASCII.GetString($buf, 0, $n)) }
    }
}

function _ss($line, $waitMs) {
    Write-Host "`n>>> $line"
    $p.WriteLine($line)
    Start-Sleep -Milliseconds $waitMs
    _rr (300 + $waitMs)
}

_rr 2000
_ss "" 800
_ss "reset" 3500
_rr 5000
$p.Close()
Write-Host "`n=== Done ==="
