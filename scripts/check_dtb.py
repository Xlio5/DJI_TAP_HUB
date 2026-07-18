"""Check DTB structure"""
import struct, os, tarfile

# Extract from tar
with tarfile.open(r"c:\my_project\TUN_NAT_HUB\backup\tun_nat_hub_v3s_backup.tar.gz", "r:gz") as tar:
    f = tar.extractfile("./sun8i-v3s-licheepi-zero-dock.dtb")
    d = f.read()

magic = struct.unpack(">I", d[0:4])[0]
total = struct.unpack(">I", d[4:8])[0]
off_dt_struct = struct.unpack(">I", d[8:12])[0]
off_dt_strings = struct.unpack(">I", d[12:16])[0]
off_mem_rsvmap = struct.unpack(">I", d[16:20])[0]
version = struct.unpack(">I", d[20:24])[0]
last_comp = struct.unpack(">I", d[24:28])[0]
boot_cpuid = struct.unpack(">I", d[28:32])[0]

print("File size:", len(d))
print("Magic:    0x{:08x}".format(magic), "(expected 0xd00dfeed)")
print("Totalsize:", total, "(should match file size = {})".format("OK" if total == len(d) else "MISMATCH!"))
print("off_dt_struct:", off_dt_struct)
print("off_dt_strings:", off_dt_strings)
print("off_mem_rsvmap:", off_mem_rsvmap)
print("version:", version)
print("last_comp_version:", last_comp)
print("boot_cpuid:", boot_cpuid)

# Also check the E: copy
dtb_on_sd = r"E:\sun8i-v3s-licheepi-zero-dock.dtb"
if os.path.exists(dtb_on_sd):
    with open(dtb_on_sd, "rb") as f2:
        d2 = f2.read()
    magic2 = struct.unpack(">I", d2[0:4])[0]
    total2 = struct.unpack(">I", d2[4:8])[0]
    print("\nSD card DTB:")
    print("File size:", len(d2))
    print("Magic:    0x{:08x} {}".format(magic2, "OK" if magic2 == 0xd00dfeed else "BAD"))
    print("Totalsize:", total2, "vs file", len(d2), "{}".format("MATCH" if total2 == len(d2) else "MISMATCH"))
