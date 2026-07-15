"""上传 SPI 镜像 → 烧录 → 设 SPI bootcmd → 重启"""
import paramiko, time

SPI_FILE = r"c:\my_project\TUN_NAT_HUB\backup\spi_image.bin"
V3S = "192.168.144.66"

with open(SPI_FILE, "rb") as f:
    spi_data = f.read()
print(f"SPI image: {len(spi_data)} bytes")

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect(V3S, username="root", password="root", timeout=10)
print("SSH OK")

# 1. Upload
chan = ssh.get_transport().open_session()
chan.exec_command("cat > /tmp/spi.bin && echo WRITE_OK")
time.sleep(0.2)
CHUNK = 65536
for i in range(0, len(spi_data), CHUNK):
    chan.sendall(spi_data[i:i+CHUNK])
    if i % (4*1024*1024) == 0:
        print(f"  {i//1024//1024}MB / {len(spi_data)//1024//1024}MB")
chan.shutdown_write()
time.sleep(3)
result = chan.recv(4096).decode(errors="replace")
print(f"Upload: {result.strip()}")
chan.close()

# 2. Verify
_, o, e = ssh.exec_command("wc -c /tmp/spi.bin", timeout=5)
out = o.read().decode().strip()
print(f"Verify: {out}")

if str(len(spi_data)) not in out:
    print("SIZE MISMATCH!")
    ssh.close()
    exit(1)

# 3. Flash SPI
print("Flashing SPI...")
_, o, e = ssh.exec_command(
    "dd if=/tmp/spi.bin of=/dev/mtd0 bs=4096 2>&1; echo FLASH_DONE",
    timeout=60
)
print(o.read().decode().strip())

# 4. Set U-Boot env for SPI boot (write to SPI env offset)
# SPL will load U-Boot proper, env is stored at the fat env location
# For SPI: write env vars to SPI flash
print("Setting SPI bootcmd...")

# Calculate bootcmd addresses from the image layout
# DTB @ 1MB = 0x100000, zImage @ 1.1MB = 0x119800, zImage size = 0x5a7888
bootargs = "console=ttyS0,115200 root=/dev/mtdblock4 rootfstype=squashfs g_serial.idVendor=0x0BDA g_serial.idProduct=0x8812 g_serial.use_acm=0 mtdparts=spi32766.0:1M(uboot),64k(dtb),5790k(kernel),-(rootfs)"
bootcmd = "sf probe 0; sf read 0x42000000 0x100000 0x4000; sf read 0x41000000 0x119800 0x5a7888; bootz 0x41000000 - 0x42000000"

_, o, e = ssh.exec_command(
    f"fw_setenv bootargs '{bootargs}' && "
    f"fw_setenv bootcmd '{bootcmd}' && "
    "fw_printenv && echo ENV_DONE",
    timeout=10
)
print(o.read().decode())
err = e.read().decode()
if "not found" in err:
    print("fw_printenv not available - will set env from U-Boot manually later")
elif err:
    print("Env err:", err[:200])

# 5. All done - ready to reboot
print("\n=== READY ===")
print("SPI flashed + env set. Remove SD card, then:")
print("ssh.exec_command('reboot -f')")

ssh.close()
