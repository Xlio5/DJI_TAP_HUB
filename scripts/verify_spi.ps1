$p = New-Object System.IO.Ports.SerialPort "COM10", 115200, None, 8, One
$p.ReadTimeout = 200
$p.Open()
Write-Host "=== SPI Flash 逐分区验证 ==="

function Dr($ms) {
    $end = (Get-Date).AddMilliseconds($ms)
    $buf = New-Object byte[] 8192
    while ((Get-Date) -lt $end) {
        try { $n = $p.Read($buf, 0, $buf.Length) } catch { Start-Sleep -Milliseconds 100; continue }
        if ($n -gt 0) { Write-Host -NoNewline ([System.Text.Encoding]::ASCII.GetString($buf, 0, $n)) }
    }
}

function Sc($line, $afterMs) {
    Write-Host "`n=== $line ==="
    $p.WriteLine($line)
    Start-Sleep -Milliseconds $afterMs
    Dr (500 + $afterMs)
}

Dr 500

# 1. SPL header @ offset 0 (Boot ROM requirement)
Sc "echo '--- [1] SPL @ 0x000000-0x007FFF ---'" 500
Sc "dd if=/dev/mtd0 bs=1 count=32 skip=0 2>/dev/null | hexdump -C" 1000
Sc "echo '  Expect: ea000016 = ARM jump, eGON.BT0 = eGON signature'" 500

# 2. U-Boot @ offset 0x8000 (CONFIG_SYS_SPI_U_BOOT_OFFS)
Sc "echo '--- [2] U-Boot @ 0x008000 ---'" 500
Sc "dd if=/dev/mtd0 bs=1 count=16 skip=32768 2>/dev/null | hexdump -C" 1000
Sc "echo '  Expect: non-zero data (U-Boot binary starts here)'" 500

# 3. U-Boot ENV @ offset 0x7E000 (backup env)
Sc "echo '--- [3] ENV @ 0x07E000 ---'" 500
Sc "dd if=/dev/mtd0 bs=1 count=64 skip=516096 2>/dev/null | hexdump -C" 1000
Sc "echo '  Expect: bootargs or bootcmd text'" 500

# 4. DTB @ offset 0x100000 (mtdpart "dtb")
Sc "echo '--- [4] DTB @ 0x100000 (mtd dtb partition) ---'" 500
Sc "dd if=/dev/mtd0 bs=1 count=16 skip=1048576 2>/dev/null | hexdump -C" 1000
Sc "echo '  Expect: d00dfeed = DTB magic'" 500

# 5. Kernel @ offset 0x110000 (mtdpart "kernel")
Sc "echo '--- [5] zImage @ 0x110000 (mtd kernel partition) ---'" 500
Sc "dd if=/dev/mtd0 bs=1 count=64 skip=1114112 2>/dev/null | hexdump -C" 1000
Sc "echo '  Expect: zImage header (check for Linux ARM boot marker)'" 500

# 6. rootfs @ offset 0x710000 (mtdpart "rootfs")
Sc "echo '--- [6] rootfs @ 0x710000 (mtd rootfs partition) ---'" 500
Sc "dd if=/dev/mtd0 bs=1 count=64 skip=7405568 2>/dev/null | hexdump -C" 1000
Sc "echo '  Expect: hsqs = squashfs magic, then size/compression info'" 500

# 7. Partition table summary
Sc "echo '--- [7] MTD partition map ---'" 500
Sc "cat /proc/mtd 2>/dev/null || echo /proc/mtd not mounted" 1000

# 8. Check there's usable data after rootfs (OTA space)
Sc "echo '--- [8] Free space after rootfs (OTA area) ---'" 500
Sc "dd if=/dev/mtd0 bs=1 count=16 skip=11554816 2>/dev/null | hexdump -C" 1000
Sc "echo '  Expect: FF (erased NOR) or padding'" 500

$p.Close()
Write-Host "`n=== SPI verification complete ==="
