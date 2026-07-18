#!/bin/bash
echo "=== U-Boot ==="
cd /home/xlong/v3s/u-boot
echo "U-Boot dir: $(pwd)"
echo "Branch: $(git branch --show-current 2>/dev/null || echo 'N/A')"
echo "SPL exists: $(test -f spl/sunxi-spl.bin && echo YES || echo NO)"
ls -lh spl/sunxi-spl.bin 2>/dev/null || echo "  (not built)"
echo "U-Boot exists: $(test -f u-boot.bin && echo YES || echo NO)"
ls -lh u-boot.bin 2>/dev/null || echo "  (not built)"

echo ""
echo "=== SPL preload patch check ==="
if grep -q "TUN_NAT_HUB" arch/arm/mach-sunxi/spl_spi_sunxi.c 2>/dev/null; then
  echo "SPL preload patch: PRESENT"
  grep -A3 "TUN_NAT_HUB" arch/arm/mach-sunxi/spl_spi_sunxi.c
else
  echo "SPL preload patch: MISSING - needs to be applied!"
fi

echo ""
echo "=== Buildroot ==="
cd /home/xlong/v3s/buildroot-2024.02
echo "Buildroot dir: $(pwd)"
echo "Rootfs exists: $(test -f output/images/rootfs.squashfs && echo YES || echo NO)"
ls -lh output/images/rootfs.squashfs 2>/dev/null || echo "  (not built)"
echo "Target web_server: $(test -f output/target/root/web_server && echo YES || echo NO)"
ls -lh output/target/root/web_server 2>/dev/null || echo "  (missing)"

echo ""
echo "=== Check S99tun_nat_hub init script ==="
find output/target/etc -name "S99*" -o -name "S??tun*" 2>/dev/null | head -5
find output/target -maxdepth 5 -name "S*tun*" 2>/dev/null | head -5

echo ""
echo "=== g_serial.ko ==="
find output/target -name "g_serial.ko" 2>/dev/null
