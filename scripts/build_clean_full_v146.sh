#!/bin/bash
# 完整 clean 编译 v1.4.6 固件 + rootfs + 16MB spi_image
set -e
cd /mnt/c/my_project/TUN_NAT_HUB
GCC=arm-linux-gnueabihf-gcc
GPP=arm-linux-gnueabihf-g++

echo "=== [1/4] clean 编译所有 C 库 ==="
rm -rf /tmp/build_clean && mkdir -p /tmp/build_clean
for f in duml rc_decode chmap sbus crsf rc_map; do
    echo "  gcc ${f}.c"
    CCACHE_DISABLE=1 $GCC -O2 -c -o "/tmp/build_clean/${f}.o" "ubuntu/src/${f}.c"
done

echo "=== [2/4] 编译 web_server + dji_rc + usb_tund ==="
CCACHE_DISABLE=1 $GPP -std=c++17 -Os -s -static \
    -o ubuntu/build_v3s/web_server ubuntu/src/web_server.cpp \
    /tmp/build_clean/rc_map.o /tmp/build_clean/rc_decode.o -lpthread
echo "  web_server: $(stat -c%s ubuntu/build_v3s/web_server) bytes"

CCACHE_DISABLE=1 $GPP -std=c++17 -O2 -s \
    -o ubuntu/build_v3s/dji_rc ubuntu/src/dji_rc.cpp \
    /tmp/build_clean/*.o -lpthread
echo "  dji_rc: $(stat -c%s ubuntu/build_v3s/dji_rc) bytes"

if [ -f ubuntu/src/usb_tund.cpp ] || [ -f ubuntu/src/usb_tund.c ]; then
    if [ -f ubuntu/src/usb_tund.cpp ]; then
        CCACHE_DISABLE=1 $GPP -std=c++17 -O2 -s -o ubuntu/build_v3s/usb_tund ubuntu/src/usb_tund.cpp -lpthread
    else
        CCACHE_DISABLE=1 $GCC -O2 -s -o ubuntu/build_v3s/usb_tund ubuntu/src/usb_tund.c
    fi
    echo "  usb_tund: $(stat -c%s ubuntu/build_v3s/usb_tund) bytes"
else
    echo "  无 usb_tund 源码, 从旧 rootfs 保留"
fi

echo ""
echo "=== [3/4] 打包 rootfs_v146.squashfs ==="
bash scripts/build_rootfs_v146.sh 2>&1 | tail -4

echo ""
echo "=== [4/4] 生成 16MB spi_image_v146.bin ==="
python3 scripts/build_spi_image.py backup/rootfs_v146.squashfs backup/spi_image_v146.bin 2>&1 | tail -6

echo ""
echo "=== 产物 ==="
md5sum ubuntu/build_v3s/web_server ubuntu/build_v3s/dji_rc
md5sum backup/rootfs_v146.squashfs backup/spi_image_v146.bin
echo "DONE"
