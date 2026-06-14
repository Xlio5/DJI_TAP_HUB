"""Rewrite install.sh with correct UTF-8 encoding."""
import os

content = """#!/bin/bash
# TUN_NAT_HUB — One-Click Install Script
# Target: RK3588 (Rock 5C) Ubuntu ARM64
# Usage: sudo bash install.sh
set -e

echo "========================================="
echo " TUN_NAT_HUB Installer v1.0"
echo " Target: RK3588 (ARM64) + g_serial USB"
echo "========================================="

if [ "$(id -u)" != "0" ]; then
    echo "ERROR: Please run with sudo"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
XHOME="/home/xlong"

# Ensure xlong home directory exists
if [ ! -d "$XHOME" ]; then
    echo "Creating $XHOME ..."
    mkdir -p "$XHOME"
    chown xlong:xlong "$XHOME" 2>/dev/null || true
fi

# — Step 1: Stop existing services —
echo "[1/6] Stopping existing services..."
systemctl stop tun_nat_hub 2>/dev/null || true
systemctl stop tun_web 2>/dev/null || true

# — Step 2: Install binary —
echo "[2/6] Installing usb_tund daemon..."
cp "$SCRIPT_DIR/bin/usb_tund" /usr/local/bin/usb_tund
chmod 755 /usr/local/bin/usb_tund
file /usr/local/bin/usb_tund

# — Step 3: Install shell scripts —
echo "[3/6] Installing setup scripts..."
for f in setup_gadget.sh setup_nat.sh; do
    cp "$SCRIPT_DIR/scripts/$f" "/usr/local/bin/$f"
    chmod 755 "/usr/local/bin/$f"
    # Remove Windows CRLF carriage returns
    sed -i 's/\r$//' "/usr/local/bin/$f"
done

# — Step 4: Install systemd services —
echo "[4/6] Installing systemd services..."
cp "$SCRIPT_DIR/config/tun_nat_hub.service" /etc/systemd/system/tun_nat_hub.service
cp "$SCRIPT_DIR/config/tun_web.service" /etc/systemd/system/tun_web.service
sed -i 's/\r$//' /etc/systemd/system/tun_nat_hub.service
sed -i 's/\r$//' /etc/systemd/system/tun_web.service
systemctl daemon-reload

# — Step 5: Install web panel + echo server —
echo "[5/6] Installing web panel + TCP echo server..."
cp "$SCRIPT_DIR/web/web_panel.py" "$XHOME/web_panel.py"
cp "$SCRIPT_DIR/web/echo_srv.py" "$XHOME/echo_srv.py"
sed -i 's/\r$//' "$XHOME/web_panel.py"
sed -i 's/\r$//' "$XHOME/echo_srv.py"
chown xlong:xlong "$XHOME/web_panel.py" "$XHOME/echo_srv.py" 2>/dev/null || true

# — Step 6: Enable and start services —
echo "[6/6] Enabling and starting services..."
systemctl enable tun_nat_hub
systemctl enable tun_web
systemctl start tun_nat_hub
sleep 2
systemctl start tun_web 2>/dev/null || true

echo ""
echo "========================================="
echo " Installation Complete!"
echo "========================================="
echo ""
echo " Service Status:"
echo "   tun_nat_hub : $(systemctl is-active tun_nat_hub)"
echo "   tun_web     : $(systemctl is-active tun_web)"
echo ""
echo " Management:"
echo "   systemctl status tun_nat_hub"
echo "   systemctl status tun_web"
echo "   journalctl -u tun_nat_hub -f"
echo ""

LAN_IP=$(ip -br addr show 2>/dev/null | grep -v 'lo\|tun\|docker\|veth' | awk '{print $3}' | head -1 | cut -d/ -f1)
echo " Web Panel:  http://${LAN_IP}:8080"
echo " SSH:        ssh xlong@${LAN_IP}  (password: 1234)"
echo "========================================="
"""

path = r"c:\my_project\TUN_NAT_HUB\tun_nat_hub_pkg\install.sh"
with open(path, "wb") as f:
    f.write(content.encode("utf-8"))

# Also ensure it ends with single LF
with open(path, "rb") as f:
    data = f.read()
# Strip any trailing CR or LF then add single LF
data = data.rstrip(b"\r\n") + b"\n"
with open(path, "wb") as f:
    f.write(data)

crlf = b"\r\n"
print(f"Size: {len(data)} bytes")
print(f"Has CRLF: {crlf in data}")
print("OK - install.sh written with correct encoding")
