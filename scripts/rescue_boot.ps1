$p = New-Object System.IO.Ports.SerialPort "COM10", 115200, None, 8, One
$p.ReadTimeout = 200
$p.Open()
Write-Host "=== V3s Rescue Boot ==="

function Drain($ms) {
    $end = (Get-Date).AddMilliseconds($ms)
    $buf = New-Object byte[] 8192
    while ((Get-Date) -lt $end) {
        try { $n = $p.Read($buf, 0, $buf.Length) } catch { Start-Sleep -Milliseconds 100; continue }
        if ($n -gt 0) { Write-Host -NoNewline ([System.Text.Encoding]::ASCII.GetString($buf, 0, $n)) }
    }
}

function Cmd($line, $afterMs) {
    Write-Host "`n=== CMD: $line ==="
    $p.WriteLine($line)
    Start-Sleep -Milliseconds $afterMs
    Drain (500 + $afterMs)
}

# Drain any pending output
Drain 500

# Step 1: Load kernel
Cmd "fatload mmc 0:1 0x41000000 zImage" 4000

# Step 2: Load DTB (12695 bytes with SPI NOR)
Cmd "fatload mmc 0:1 0x42000000 sun8i-v3s-licheepi-zero-dock.dtb" 1500

# Step 3: Load rescue initramfs v4
Cmd "fatload mmc 0:1 0x42200000 rescue.cpio.gz" 2000

# Step 4: Set FDT
Cmd "fdt addr 0x42000000" 500

# Step 5: Boot
Cmd "setenv bootargs console=ttyS0,115200 rdinit=/init" 500
Cmd "bootz 0x41000000 0x42200000:`$`{filesize`} 0x42000000" 1000

# Step 6: Watch rescue run
Write-Host "`n=== Waiting for rescue to run (60s)... ==="
Drain 60000

$p.Close()
Write-Host "`n=== Done ==="
