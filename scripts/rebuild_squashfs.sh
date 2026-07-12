#!/bin/bash
set -e

echo "=== Rebuilding squashfs with TUN_NAT_HUB + SPI NOR DTB ==="

# 1. Extract rootfs
echo "Step 1: Extracting rootfs..."
rm -rf /tmp/clean_root
mkdir -p /tmp/clean_root
tar xf /home/xlong/v3s/buildroot-2024.02/output/images/rootfs.tar -C /tmp/clean_root/

# 2. Create dirs and copy TUN_NAT_HUB files
echo "Step 2: Copying TUN_NAT_HUB files..."
mkdir -p /tmp/clean_root/usr/local/bin
mkdir -p /tmp/clean_root/etc/init.d
cp /mnt/c/my_project/TUN_NAT_HUB/ubuntu/build_v3s/web_server /tmp/clean_root/usr/local/bin/
cp /mnt/c/my_project/TUN_NAT_HUB/ubuntu/build_v3s/usb_tund /tmp/clean_root/usr/local/bin/
cp /mnt/c/my_project/TUN_NAT_HUB/ubuntu/scripts/setup_v3s.sh /tmp/clean_root/usr/local/bin/
cp /mnt/c/my_project/TUN_NAT_HUB/ubuntu/scripts/S99tun_nat_hub_clean /tmp/clean_root/etc/init.d/S99tun_nat_hub
chmod +x /tmp/clean_root/usr/local/bin/web_server
chmod +x /tmp/clean_root/usr/local/bin/usb_tund
chmod +x /tmp/clean_root/usr/local/bin/setup_v3s.sh
chmod +x /tmp/clean_root/etc/init.d/S99tun_nat_hub

# 3. Remove python3 leftovers
echo "Step 3: Cleaning python3 leftovers..."
rm -rf /tmp/clean_root/usr/lib/python3* 2>/dev/null || true
rm -f /tmp/clean_root/usr/bin/python* 2>/dev/null || true

echo "Files in /usr/local/bin:"
ls -la /tmp/clean_root/usr/local/bin/
echo "Files in /etc/init.d:"
ls -la /tmp/clean_root/etc/init.d/

# 4. Create squashfs
echo "Step 4: Creating squashfs..."
rm -f /tmp/clean.squashfs
mksquashfs /tmp/clean_root /tmp/clean.squashfs -comp xz -b 128K -noappend 2>&1
ls -lh /tmp/clean.squashfs

# 5. Restore DTS and add SPI NOR
echo "Step 5: Patching DTS with SPI NOR..."
cd /home/xlong/v3s/linux
cp arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dts arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dts.spi

cat >> arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dts << 'DTSEOF'

/* SPI NOR Flash (w25q128 @ SPI0) */
&spi0 {
	#address-cells = <1>;
	#size-cells = <0>;
	cs-gpios = <0>;
	status = "okay";

	flash@0 {
		compatible = "jedec,spi-nor";
		reg = <0>;
		#address-cells = <1>;
		#size-cells = <1>;
		label = "firmware";
		spi-max-frequency = <40000000>;
	};
};
DTSEOF

make ARCH=arm CROSS_COMPILE=arm-linux-gnueabihf- dtbs 2>&1 | tail -3

# 6. Copy to project backup
echo "Step 6: Copying to project..."
cp /tmp/clean.squashfs /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs.squashfs
cp arch/arm/boot/dts/allwinner/sun8i-v3s-licheepi-zero-dock.dtb /mnt/c/my_project/TUN_NAT_HUB/backup/sun8i-v3s-licheepi-zero-dock.dtb

ls -lh /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs.squashfs
ls -lh /mnt/c/my_project/TUN_NAT_HUB/backup/sun8i-v3s-licheepi-zero-dock.dtb

echo "=== DONE ==="
