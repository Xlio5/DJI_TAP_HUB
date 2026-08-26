#!/bin/bash
# 诊断 UART0 debug 映射：对比各 SPI 镜像 bootargs + rootfs S99
set +e

echo "========== 1. 各 SPI 镜像 env 区 console 参数 =========="
for img in \
  backup/spi_image_v1638_20260823_txhz_debug.bin \
  backup/spi_image_v1637_20260823_uart0_debug_restore.bin \
  backup/spi_image_v1634_sc16.bin \
  backup/spi_image_v9.bin \
  backup/spi_image_sc16.bin ; do
  echo "----- $img -----"
  dd if="$img" bs=1 skip=$((0x7E000)) count=$((0x2000)) 2>/dev/null | tr -d '\0' | tr '\xff' '\n' | grep -iE '^bootargs|console=|root=' | head -4
done

echo
echo "========== 2. v1638 env 原始可读串 =========="
dd if=backup/spi_image_v1638_20260823_txhz_debug.bin bs=1 skip=$((0x7E000)) count=$((0x2000)) 2>/dev/null | tr -d '\0' | tr '\xff' '\n' | grep -vE '^\s*$' | head -10

echo
echo "========== 3. rootfs S99 与仓库 S99 对比 =========="
R=/tmp/rfs_v1638/etc/init.d/S99tun_nat_hub
if [ -f "$R" ]; then
  diff "$R" /mnt/c/my_project/TUN_NAT_HUB/ubuntu/scripts/S99tun_nat_hub && echo "IDENTICAL"
else
  echo "rootfs S99 不存在: $R"
  ls -la /tmp/rfs_v1638/etc/init.d/
fi

echo
echo "========== 4. rootfs 内 dji_rc 启动命令 (S99 dji_rc 行) =========="
grep -n 'dji_rc' "$R" 2>/dev/null | head

echo
echo "========== 5. rootfs inittab 里 ttyS0 行 =========="
grep -n 'ttyS0\|console' /tmp/rfs_v1638/etc/inittab 2>/dev/null
