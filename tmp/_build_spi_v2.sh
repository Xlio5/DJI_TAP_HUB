#!/bin/bash
# 打包完整 spi_image v2: 新 U-Boot + 内核 + rootfs_v2
set -e
cd /mnt/c/my_project/TUN_NAT_HUB
python3 -B scripts/build_spi_image.py backup/rootfs_v2.squashfs backup/spi_image_v2.bin 2>&1 | tail -12
echo ""
echo "=== 校验 bootcmd + host key ==="
python3 -c "
import subprocess
# 从镜像提取 U-Boot 段检查 bootcmd
d = open('backup/spi_image_v2.bin','rb').read()
seg = d[0x8000:0x8000+404384]
print('bootcmd PB6:', b'gpio input PB6' in seg)
print('console 115200:', b'console=ttyS0,115200' in seg)
print('console null:', b'console=null' in seg)
# rootfs host key
import os
print('镜像大小:', len(d))
"
echo "DONE"
