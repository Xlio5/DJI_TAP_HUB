param($PortName="COM10", $Baud=115200)

$port = New-Object System.IO.Ports.SerialPort $PortName, $Baud, None, 8, One
$port.ReadTimeout = 500
$port.Open()
Write-Host "Connected to $PortName"

function WaitRead($ms) {
    $end = (Get-Date).AddMilliseconds($ms)
    $buf = New-Object byte[] 4096
    while ((Get-Date) -lt $end) {
        try { $n = $port.Read($buf, 0, $buf.Length) } catch { break }
        if ($n -gt 0) { Write-Host -NoNewline ([System.Text.Encoding]::ASCII.GetString($buf, 0, $n)) }
    }
}

function SendLine($line, $waitMs) {
    Write-Host "`n>>> $line"
    $port.WriteLine($line)
    Start-Sleep -Milliseconds $waitMs
    WaitRead (500 + $waitMs)
}

WaitRead 1000
SendLine "" 300
SendLine "hexdump -C -n 32 /dev/mtd0" 1500
SendLine "dd if=/dev/mtd0 bs=4096 skip=1808 count=1 2>/dev/null | hexdump -C -n 16" 2000
SendLine "dd if=/dev/mtd0 bs=4096 skip=272 count=1 2>/dev/null | hexdump -C -n 16" 2000

$port.Close()
Write-Host "`n=== Done ==="
