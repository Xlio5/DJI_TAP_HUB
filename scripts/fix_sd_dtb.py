"""Fix SD card DTB from backup tar"""
import tarfile, os

dtb_path = r"E:\sun8i-v3s-licheepi-zero-dock.dtb"

# Delete bad DTB
try:
    os.remove(dtb_path)
    print("Removed bad DTB")
except:
    pass

# Extract good DTB from backup
with tarfile.open(r"c:\my_project\TUN_NAT_HUB\backup\tun_nat_hub_v3s_backup.tar.gz", "r:gz") as tar:
    f = tar.extractfile("./sun8i-v3s-licheepi-zero-dock.dtb")
    data = f.read()

with open(dtb_path, "wb") as out:
    out.write(data)

print("DTB written:", os.path.getsize(dtb_path), "bytes")

# Verify magic
with open(dtb_path, "rb") as v:
    magic = v.read(4)
print("Magic:", magic.hex(), "-", "OK" if magic.hex() == "d00dfeed" else "BAD")

# List E: contents
print("\nE: contents:")
for f in sorted(os.listdir("E:")):
    if "Volume" not in f:
        sz = os.path.getsize(os.path.join("E:", f))
        print("  {:50s} {:>8,} bytes".format(f, sz))
