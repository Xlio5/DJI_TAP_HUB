#!/bin/bash
export PATH="/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

echo "============================================"
echo "  SPI FLASH BYTE-LEVEL AUDIT"
echo "============================================"
echo ""

echo "--- 1. SPL @ 0x000000 ---"
dd if=/dev/mtd0 bs=1 count=32 skip=0 2>/dev/null | hexdump -C
echo "EXPECT: ea000016 + eGON.BT0 + SPL."

echo ""
echo "--- 2. U-Boot @ 0x008000 ---"
dd if=/dev/mtd0 bs=1 count=32 skip=32768 2>/dev/null | hexdump -C
echo "EXPECT: ARM vector table (not all FF/00)"

echo ""
echo "--- 3. U-Boot ENV @ 0x07E000 ---"
dd if=/dev/mtd0 bs=1 count=128 skip=516096 2>/dev/null | hexdump -C
echo "EXPECT: bootargs=console=... text"

echo ""
echo "--- 4. DTB @ 0x100000 ---"
dd if=/dev/mtd0 bs=1 count=16 skip=1048576 2>/dev/null | hexdump -C
echo "EXPECT: d00dfeed = DTB magic"

echo ""
echo "--- 5. Kernel @ 0x110000 ---"
dd if=/dev/mtd0 bs=1 count=64 skip=1114112 2>/dev/null | hexdump -C
echo "EXPECT: zImage header + 0x016f2818 magic"

echo ""
echo "--- 6. rootfs @ 0x710000 ---"
dd if=/dev/mtd0 bs=1 count=64 skip=7405568 2>/dev/null | hexdump -C
echo "EXPECT: hsqs + squashfs header"

echo ""
echo "--- 7. rootfs can be mounted? ---"
mkdir -p /tmp/spi_root
mount -t squashfs /dev/mtdblock3 /tmp/spi_root 2>&1
if [ $? -eq 0 ]; then
  echo "MOUNT OK!"
  echo ""
  echo "=== rootfs contents ==="
  ls /tmp/spi_root/etc/init.d/S* 2>/dev/null
  ls -lh /tmp/spi_root/usr/local/bin/web_server 2>/dev/null
  ls -lh /tmp/spi_root/usr/local/bin/usb_tund 2>/dev/null
  umount /tmp/spi_root
else
  echo "MOUNT FAILED!"
fi

echo ""
echo "============================================"
echo "  AUDIT COMPLETE"
echo "============================================"
