"""Write SPL+U-Boot to SD card sector 8 (requires admin)"""
import os

DISK = r'\\.\PhysicalDrive2'
SRC = r'c:\my_project\TUN_NAT_HUB\backup\u-boot-sunxi-with-spl.bin'

# Confirm with user
print("=" * 60)
print("Writing u-boot-sunxi-with-spl.bin to SD card sector 8")
print("Target:", DISK)
print("=" * 60)

with open(SRC, 'rb') as f:
    data = f.read()

print("Source: %d bytes (%.1f KB)" % (len(data), len(data)/1024))
print("SPL header: %s %s" % (data[0:4].hex(), data[4:12].decode('ascii','replace')))

response = input("\nEnter YES to confirm write: ")
if response != "YES":
    print("Aborted.")
    exit(0)

try:
    disk = open(DISK, 'r+b')

    # Read current sector 0 (MBR) first - we must preserve it
    disk.seek(0)
    mbr = disk.read(512)
    print("Current MBR sig: %02X%02X" % (mbr[510], mbr[511]))

    # Write SPL+U-Boot at sector 8 (offset 4096)
    disk.seek(4096)
    disk.write(data)
    disk.flush()

    # Verify
    disk.seek(4096)
    verify = disk.read(64)
    disk.close()

    ok = all(data[i] == verify[i] for i in range(64))
    msg = ""
    if ok:
        msg = "SUCCESS"
    else:
        msg = "FAIL"
    print("\n" + ("=" * 60))
    print(msg)
    print("=" * 60)
    try:
        with open(r"c:\my_project\TUN_NAT_HUB\scripts\write_result.txt", "w") as lf:
            lf.write("Write: %s\nVerify: %s\n" % (msg, verify[0:32].hex()))
    except:
        pass
except Exception as e:
    err = "\nERROR: %s" % str(e)
    print(err)
    try:
        with open(r"c:\my_project\TUN_NAT_HUB\scripts\write_result.txt", "w") as lf:
            lf.write(err)
    except:
        pass

# Also log to file
try:
    with open(r"c:\my_project\TUN_NAT_HUB\scripts\write_result.txt", "a") as lf:
        lf.write("\nScript finished.\n")
except:
    pass

input("\nPress Enter to exit...")
