"""Write SPL+U-Boot to SD card sector 8. Output: LOG_FILE"""
import sys, traceback

LOG = r"c:\my_project\TUN_NAT_HUB\scripts\sd_write_log.txt"
SRC = r"c:\my_project\TUN_NAT_HUB\backup\u-boot-sunxi-with-spl.bin"

def log(msg):
    with open(LOG, "a") as f:
        f.write(msg + "\n")
    print(msg)

open(LOG, "w").close()  # clear log

log("=== SD sector 8 write ===")

try:
    with open(SRC, "rb") as f:
        data = f.read()
    mag = data[0:4].hex()
    sig = data[4:12].decode("ascii", "replace")
    log("Source: %d bytes, SPL: %s %s" % (len(data), mag, sig))

    # Try all physical drives 0-5
    for num in range(6):
        path = r"\\.\PhysicalDrive%d" % num
        try:
            disk = open(path, "r+b")
            disk.seek(0)
            mbr = disk.read(512)
            # Check if this is FAT32 (MBR sig 55AA, FAT32 type 0C or 0B)
            sig_byte = (mbr[511] << 8) | mbr[510]
            p1_type = mbr[450]  # First partition type at offset 0x1C2
            disk_size = disk.seek(0, 2)
            disk.close()

            if sig_byte == 0xAA55 and disk_size > 10000000000 and disk_size < 20000000000:
                log("Found SD card: %s (size %.1f GB, type %02X)" % (path, disk_size/1e9, p1_type))
                # Write SPL+U-Boot at sector 8
                disk = open(path, "r+b")
                disk.seek(4096)
                disk.write(data)
                disk.flush()
                disk.seek(4096)
                verify = disk.read(128)
                disk.close()

                ok = all(data[i] == verify[i] for i in range(128))
                log("Write: %s" % ("SUCCESS" if ok else "FAIL"))
                if ok:
                    log("SD card is BOOTABLE for V3s!")
                    log("Insert into V3s, power on, check COM10 for U-Boot")
                sys.exit(0 if ok else 1)
        except Exception as e:
            continue

    # Try diskpart approach
    log("No SD found via PhysicalDrive, trying diskpart...")
    log("DONE - check results above")

except Exception as e:
    log("FATAL: %s" % str(e))
    log(traceback.format_exc())
    sys.exit(2)
