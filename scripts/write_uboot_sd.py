"""直接写 U-Boot 到 SD 卡物理磁盘 8KB 偏移 (Disk 2)"""
import subprocess

# Read U-Boot from WSL
uboot = subprocess.check_output(["wsl", "bash", "-c", "cat /home/xlong/v3s/u-boot/u-boot-sunxi-with-spl.bin"])
print(f"U-Boot: {len(uboot)} bytes")

# Write to SD card PhysicalDrive2 at 8KB offset
# Must run as admin!
disk_path = r"\\.\PhysicalDrive2"
try:
    f = open(disk_path, "rb+")
    f.seek(8 * 1024)  # 8KB offset for SD card
    f.write(uboot)
    f.flush()
    f.close()
    print(f"U-Boot written to {disk_path} at offset 8KB")
    print("SD card is now bootable! Insert into V3s and power on.")
except PermissionError:
    print("ERROR: Need admin rights!")
    print("Right-click PowerShell -> Run as Administrator, then:")
    print(f"  python {__file__}")
except Exception as e:
    print(f"ERROR: {e}")
