#!/bin/bash
cd /home/xlong/v3s/linux

echo "=== Missing Config Checks ==="
for k in MTD_CMDLINE_PARTS MTD_OF_PARTS MTD_PARTITIONED_MASTER MTD_SPLIT_FIRMWARE; do
  val=$(grep "^CONFIG_${k}=" .config 2>/dev/null || echo "NOT SET")
  echo "  $k = $val"
done

echo ""
echo "=== g_serial as builtin (not module) ==="
echo "Current: $(grep CONFIG_USB_G_SERIAL .config)"

echo ""
echo "=== No SPI NOR in DTS? Let's check DTS ==="
DTS="/home/xlong/v3s/linux/arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dts"
if [ -f "$DTS" ]; then
  echo "DTS exists: $DTS"
  grep -A2 "spi" "$DTS" | head -20
else
  echo "DTS not found at expected path"
  find /home/xlong/v3s/linux/arch/arm/boot/dts -name "sun8i-v3s*" -type f 2>/dev/null
fi

echo ""
echo "=== Kernel Build Status ==="
echo "Kernel dir: $(pwd)"
echo "zImage exists: $(test -f arch/arm/boot/zImage && echo YES || echo NO)"
ls -lh arch/arm/boot/zImage 2>/dev/null || echo "  (not built yet)"
echo "DTB dir:"
ls -lh arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dtb 2>/dev/null || echo "  (not built yet)"
