"""Fix CRLF line endings in all package text files."""
import os

pkg = r"c:\my_project\TUN_NAT_HUB\tun_nat_hub_pkg"

files = [
    "install.sh",
    "scripts/setup_gadget.sh",
    "scripts/setup_nat.sh",
    "config/tun_nat_hub.service",
    "config/tun_web.service",
    "web/web_panel.py",
    "web/echo_srv.py",
]

for fname in files:
    path = os.path.join(pkg, fname)
    with open(path, "rb") as f:
        data = f.read()
    data = data.replace(b"\r\n", b"\n").replace(b"\r", b"")
    data = data.rstrip(b"\n") + b"\n"
    with open(path, "wb") as f:
        f.write(data)
    has_cr = b"\r" in data
    print(f"  {'OK' if not has_cr else 'WARN'} {fname} ({len(data)} bytes)")

print("Done - all text files fixed.")
