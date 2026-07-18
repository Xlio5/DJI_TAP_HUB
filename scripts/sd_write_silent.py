"""Write SPL+U-Boot to SD card sector 8 (admin, no interaction)"""
import os, sys, traceback

LOG_PATH = r"c:\my_project\TUN_NAT_HUB\scripts\sd_write.log"
DISK = r'\\.\PhysicalDrive2'
SRC = r'c:\my_project\TUN_NAT_HUB\backup\u-boot-sunxi-with-spl.bin'

def log(msg):
    with open(LOG_PATH, "a") as f:
        f.write(msg + "\n")
    print(msg)

log("Starting SD card bootable write...")
log("Target: %s" % DISK)

try:
    with open(SRC, 'rb') as f:
        data = f.read()
    log("Source: %d bytes, SPL: %s %s" % (len(data), data[0:4].hex(), data[4:12].decode('ascii','replace')))

    disk = open(DISK, 'r+b')
    # Read MBR first
    disk.seek(0)
    mbr = disk.read(512)
    log("MBR sig: %02X%02X" % (mbr[510], mbr[511]))

    # Write SPL+U-Boot at sector 8 (offset 4096)
    disk.seek(4096)
    disk.write(data)
    disk.flush()

    # Verify first 512 bytes
    disk.seek(4096)
    verify = disk.read(512)
    disk.close()

    ok = all(data[i] == verify[i] for i in range(512))
    if ok:
        log("RESULT: SUCCESS - SD card is bootable for V3s!")
        log("Verify: %s..." % verify[0:32].hex())
        log("Boot V3s with SD inserted, check COM10 for U-Boot output")
    else:
        log("RESULT: VERIFY FAILED")
        for i in range(512):
            if data[i] != verify[i]:
                log("  Mismatch at offset %d: expected %02X got %02X" % (i, data[i], verify[i]))
                break

except Exception as e:
    log("FATAL ERROR: %s" % str(e))
    log(traceback.format_exc())

log("Script finished")
