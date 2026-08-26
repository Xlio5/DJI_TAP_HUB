#!/bin/bash
set +e
R=/tmp/rfs_v1638
rm -rf "$R"
mkdir -p "$R"
unsquashfs -d "$R" /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_v1638_20260823_txhz_debug.squashfs >/dev/null 2>&1

echo "========== 1. rootfs inittab ttyS0/console 行 =========="
grep -n 'ttyS0\|console' "$R/etc/inittab"

echo
echo "========== 2. rootfs S99 与仓库 S99 diff =========="
if [ -f "$R/etc/init.d/S99tun_nat_hub" ]; then
  diff "$R/etc/init.d/S99tun_nat_hub" /mnt/c/my_project/TUN_NAT_HUB/ubuntu/scripts/S99tun_nat_hub && echo "S99 IDENTICAL"
else
  echo "rootfs S99 不存在"; ls -la "$R/etc/init.d/"
fi

echo
echo "========== 3. rootfs S99 dji_rc 启动行 =========="
grep -n 'dji_rc\|getty\|ttySC\|ttyS0' "$R/etc/init.d/S99tun_nat_hub"

echo
echo "========== 4. rootfs 内 dji_rc/web_server 是否有 ttyS0 引用 =========="
strings "$R/usr/local/bin/dji_rc" 2>/dev/null | grep -i 'ttyS0\|ttySC' | sort -u
echo "--- web_server ---"
strings "$R/usr/local/bin/web_server" 2>/dev/null | grep -i 'ttyS0\|ttySC' | sort -u

echo
echo "========== 5. rootfs 内是否有 dmesg/console 相关 =========="
ls -la "$R/usr/local/bin/dji_rc" "$R/usr/local/bin/web_server" 2>&1
echo
echo "========== 6. busybox getty 是否支持 -L 参数 (版本) =========="
"$R/bin/busybox" 2>&1 | head -3
echo
echo "========== 7. 检查 getty 是否存在其他备选路径 =========="
ls -la "$R/sbin/getty" "$R/bin/getty" 2>&1
