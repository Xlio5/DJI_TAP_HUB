#!/bin/bash
cd /home/xlong/v3s/buildroot-2024.02

echo "=== Buildroot overlay dir ==="
if [ -d board ]; then
  find board -type d -name "overlay" -o -name "rootfs*" 2>/dev/null | head -10
fi

echo ""
echo "=== BR2_ROOTFS_OVERLAY from config ==="
grep "BR2_ROOTFS_OVERLAY" .config 2>/dev/null || echo "  Not found in .config"

echo ""
echo "=== web_server source ==="
ls -lh /mnt/c/my_project/TUN_NAT_HUB/ubuntu/src/web_server.cpp 2>/dev/null || echo "  missing"
ls -lh /mnt/c/my_project/TUN_NAT_HUB/ubuntu/CMakeLists.txt 2>/dev/null || echo "  missing"

echo ""
echo "=== Buildroot packages ==="
grep -E "BR2_PACKAGE_WEBSERVER|BR2_PACKAGE_TUN|BR2_PACKAGE_GADGET" .config 2>/dev/null || echo "  No TUN_NAT_HUB packages"

echo ""
echo "=== Overlay dirs ==="
ls -la board/allwinner/ 2>/dev/null | head -10
find board -name "S99*" -o -name "g_serial*" -o -name "tun*" -o -name "web_server*" 2>/dev/null | head -10

echo ""
echo "=== Output/target check ==="
echo "etc/init.d:"
ls output/target/etc/init.d/ 2>/dev/null || echo "  (empty)"
echo "Web server:"
find output/target -name "web_server" 2>/dev/null | head -5
echo "g_serial:"
find output/target -name "*.ko" 2>/dev/null | head -5
echo "Root home:"
ls output/target/root/ 2>/dev/null | head -10

echo ""
echo "=== Config: BR2_TARGET_GENERIC_GETTY ==="
grep "BR2_TARGET_GENERIC_GETTY" .config 2>/dev/null
