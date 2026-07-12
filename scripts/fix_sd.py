import tarfile, os, shutil

DEST = "E:/"

# Extract kernel from backup
print("Extracting kernel from backup...")
with tarfile.open(r"c:\my_project\TUN_NAT_HUB\backup\tun_nat_hub_v3s_backup.tar.gz", "r:gz") as tar:
    for name in ["./zImage", "./sun8i-v3s-licheepi-zero-dock.dtb"]:
        f = tar.extractfile(name)
        if f:
            path = os.path.join(DEST, name)
            with open(path, "wb") as out:
                out.write(f.read())
            print(f"  {name}: {os.path.getsize(path)} bytes")

# Copy web_server
print("Copying web_server...")
src = r"c:\my_project\TUN_NAT_HUB\ubuntu\build_v3s\web_server"
dst = os.path.join(DEST, "web_server")
shutil.copy2(src, dst)
print(f"  web_server: {os.path.getsize(dst)} bytes")

# List
print("\nE: contents:")
for f in os.listdir(DEST):
    print(f"  {f}")
print("Done!")
