#!/bin/bash
set -e
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

echo "=== 1. Fix SPL double spi0_deinit ==="
cd /home/xlong/v3s/u-boot
python3 << 'PYEOF'
c = open("arch/arm/mach-sunxi/spl_spi_sunxi.c").read()
# Count occurrence
cnt = c.count("spi0_deinit();")
print(f"spi0_deinit count before: {cnt}")
if cnt > 1:
    # Remove the last occurrence
    last = c.rfind("spi0_deinit();")
    c2 = c[:last].rstrip()
    c2 += "\n\n\tspi0_deinit();\n"
    tail = c[last + len("spi0_deinit();"):]
    # Just keep last one, remove extras
    lines = c.split("\n")
    new_lines = []
    seen = False
    for i, line in enumerate(lines):
        if "spi0_deinit();" in line:
            if not seen:
                new_lines.append(line)
                seen = True
        else:
            new_lines.append(line)
    open("arch/arm/mach-sunxi/spl_spi_sunxi.c","w").write("\n".join(new_lines))
    print(f"Fixed: now {open('arch/arm/mach-sunxi/spl_spi_sunxi.c').read().count('spi0_deinit();')} occurrences")
PYEOF

echo ""
echo "=== 2. make clean + rebuild U-Boot ==="
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- clean 2>&1 | tail -3
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j20 2>&1 | tail -5
echo "UBoot built: $(stat -c%s spl/sunxi-spl.bin) / $(stat -c%s u-boot.bin)"
cp spl/sunxi-spl.bin u-boot.bin /mnt/c/my_project/TUN_NAT_HUB/backup/

echo ""
echo "=== 3. Verify U-Boot has root= ==="
strings u-boot.bin | grep -o "root=/dev/mtdblock3" | head -1

echo ""
echo "=== 4. Kernel make clean + rebuild ==="
cd /home/xlong/v3s/linux
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- clean 2>&1 | tail -3
sed -i 's/CONFIG_USB_G_SERIAL=m/CONFIG_USB_G_SERIAL=y/' .config
make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- -j20 zImage dtbs 2>&1 | tail -5
cp arch/arm/boot/zImage /mnt/c/my_project/TUN_NAT_HUB/backup/zImage_new
cp arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dtb /mnt/c/my_project/TUN_NAT_HUB/backup/sun8i-v3s-licheepi-zero-dock.dtb_new
echo "Kernel: $(stat -c%s arch/arm/boot/zImage) bytes"

echo ""
echo "=== 5. Build rootfs + SPI image ==="
cd /home/xlong/v3s/buildroot-2024.02
chown -R xlong:xlong output/target 2>/dev/null || true
O=board/allwinner/v3s_overlay
mkdir -p $O/etc/init.d $O/usr/local/bin $O/var/log $O/root
cp /mnt/c/my_project/TUN_NAT_HUB/ubuntu/scripts/S99tun_nat_hub $O/etc/init.d/
cp /mnt/c/my_project/TUN_NAT_HUB/ubuntu/scripts/setup_v3s_fixed.sh $O/usr/local/bin/setup_v3s.sh
chmod +x $O/etc/init.d/S99tun_nat_hub $O/usr/local/bin/setup_v3s.sh
make clean 2>&1 | tail -3
make 2>&1 | tail -20

# Compile web_server with all fixes
arm-linux-gnueabihf-g++ -std=c++17 -Os \
  -o output/target/usr/local/bin/web_server \
  /mnt/c/my_project/TUN_NAT_HUB/ubuntu/src/web_server.cpp -lpthread 2>&1 | tail -2

mksquashfs output/target /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs.squashfs -comp xz -b 1048576 -Xdict-size 1048576 -noappend 2>&1 | tail -3
echo "rootfs: $(stat -c%s /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs.squashfs) bytes"

echo ""
echo "=== 6. Build final SPI image ==="
cd /mnt/c/my_project/TUN_NAT_HUB
python3 -B scripts/build_spi_final.py 2>&1 | tail -5
echo ""
echo "=== DONE ==="
ls -lh backup/sunxi-spl.bin backup/u-boot.bin backup/zImage_new backup/rootfs.squashfs backup/spi_image.bin
