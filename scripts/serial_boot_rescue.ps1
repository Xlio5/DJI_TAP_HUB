param($PortName="COM10", $Baud=115200)

$port = New-Object System.IO.Ports.SerialPort $PortName, $Baud, None, 8, One
$port.ReadTimeout = 500
$port.Open()
Write-Host "Connected to $PortName"

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

# Wait for U-Boot prompt or kernel output
Wr 3000

# If at kernel panic, need to reset. Send Enter to try get U-Boot prompt
Sl "" 500
Sl "" 500

# Load kernel
Sl "fatload mmc 0:1 0x41000000 zImage" 3000

# Load DTB (12695 bytes with SPI NOR)
Sl "fatload mmc 0:1 0x42000000 sun8i-v3s-licheepi-zero-dock.dtb" 1000

# Load rescue v4
Sl "fatload mmc 0:1 0x42200000 rescue.cpio.gz" 1500

# Set fdt address
Sl "fdt addr 0x42000000" 500

# Boot with rescue init
Sl "setenv bootargs console=ttyS0,115200 rdinit=/init" 500
Sl "bootz 0x41000000 0x42200000:`$`{filesize`} 0x42000000" 500

# Wait for kernel boot and rescue to run
Write-Host "`n=== Waiting for rescue to complete... ==="
Wr 45000

$port.Close()
Write-Host "`n=== Done ==="
