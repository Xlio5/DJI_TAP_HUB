param($PortName="COM10", $Baud=115200)

$port = New-Object System.IO.Ports.SerialPort $PortName, $Baud, None, 8, One
$port.ReadTimeout = 500
$port.Open()
Write-Host "Connected to $PortName - reading current state..."

function Wr($ms) {
    $end = (Get-Date).AddMilliseconds($ms)
    $buf = New-Object byte[] 4096
    while ((Get-Date) -lt $end) {
        try { $n = $port.Read($buf, 0, $buf.Length) } catch { break }
        if ($n -gt 0) { Write-Host -NoNewline ([System.Text.Encoding]::ASCII.GetString($buf, 0, $n)) }
    }
}

function Sl($line, $waitMs) {
    Write-Host "`n[SEND] $line"
    $port.WriteLine($line)
    Start-Sleep -Milliseconds $waitMs
    Wr (300 + $waitMs)
}

Wr 3000

# Try to get U-Boot prompt - maybe stuck at kernel panic or shell
Sl "" 1000
Sl "reset" 3000

Wr 5000

$port.Close()
Write-Host "`n=== Done ==="
