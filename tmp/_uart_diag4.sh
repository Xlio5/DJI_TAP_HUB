#!/bin/bash
set +e
cd /mnt/c/my_project/TUN_NAT_HUB

echo "========== 1. 重新解包 旧 rootfs (backup/rootfs.squashfs) =========="
rm -rf /tmp/rfs_old
unsquashfs -d /tmp/rfs_old backup/rootfs.squashfs >/dev/null 2>&1
echo "解包完成: $(ls /tmp/rfs_old/usr/local/bin/ 2>/dev/null)"

echo
echo "========== 2. 旧 rootfs S99 关键行 =========="
grep -n 'getty\|dji_rc\|ttySC\|ttyS0\|out-dev' /tmp/rfs_old/etc/init.d/S99tun_nat_hub 2>/dev/null || echo "无匹配"

echo
echo "========== 3. 旧 rootfs dji_rc 设备引用 + 版本 =========="
strings /tmp/rfs_old/usr/local/bin/dji_rc 2>/dev/null | grep -iE 'ttyS0|ttySC|/dev/tty' | sort -u

echo
echo "========== 4. 旧 rootfs web_server 版本 =========="
strings /tmp/rfs_old/usr/local/bin/web_server 2>/dev/null | grep -oE '1\.[0-9]+\.[0-9]+' | sort -u | head

echo
echo "========== 5. 旧 rootfs inittab ttyS0 行 =========="
grep -n 'ttyS0' /tmp/rfs_old/etc/inittab 2>/dev/null

echo
echo "========== 6. git 提交里的 backup/rootfs.squashfs md5 =========="
CUR=$(md5sum backup/rootfs.squashfs | cut -d' ' -f1)
echo "工作区: $CUR"
for C in 7003deb 1f26441 dde5867; do
  M=$(git show $C:backup/rootfs.squashfs 2>/dev/null | md5sum | cut -d' ' -f1)
  echo "$C 提交内: $M"
done
