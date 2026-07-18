$p = New-Object System.IO.Ports.SerialPort "COM10", 115200, None, 8, One
$p.ReadTimeout = 500; $p.Open()
Write-Host "=== V3s Upgrade via Serial ==="

function dr($ms) { $e = (Get-Date).AddMilliseconds($ms); $b = New-Object byte[] 16384; while ((Get-Date) -lt $e) { try { $n = $p.Read($b, 0, $b.Length) } catch { break }; if ($n -gt 0) { Write-Host -NoNewline ([System.Text.Encoding]::ASCII.GetString($b, 0, $n)) } } }
function sd($c, $w) { Write-Host ">>> $c"; $p.WriteLine($c); Start-Sleep -Milliseconds $w; dr (500+$w) }

dr 500
sd "" 300

# Step 1: Download rootfs from Windows HTTP server
sd "cd /tmp && wget -q http://192.168.144.88:7777/rootfs.squashfs && echo DOWNLOAD_OK || echo DOWNLOAD_FAIL" 8000

# Step 2: Verify download
sd "ls -lh /tmp/rootfs.squashfs" 500

# Step 3: Flash rootfs
sd "echo '=== FLASHING ===' && dd if=/tmp/rootfs.squashfs of=/dev/mtd0 bs=4096 seek=1808 2>&1 && echo FLASH_OK" 8000

# Step 4: Sync
sd "sync && echo SYNC_OK" 1000

# Step 5: Verify
sd "dd if=/dev/mtd0 bs=1 count=8 skip=7405568 2>/dev/null | hexdump -C" 1000

# Step 6: Reboot
sd "echo '=== REBOOTING... ==='" 500
sd "reboot" 500

Write-Host "`n=== Done ==="
$p.Close()