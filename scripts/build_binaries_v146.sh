#!/bin/bash
# 编译 v1.4.6 固件二进制 (SBUS/CRSF 输出 + 通道映射 + 回传)
set -e
cd /mnt/c/my_project/TUN_NAT_HUB
mkdir -p ubuntu/build_v3s

echo "=== 编译 web_server (静态, 含 rc_output 配置) ==="
rm -rf /tmp/ws_o && mkdir -p /tmp/ws_o
for f in rc_map rc_decode; do
    CCACHE_DISABLE=1 arm-linux-gnueabihf-gcc -O2 -s -c -o "/tmp/ws_o/${f}.o" "ubuntu/src/${f}.c"
done
CCACHE_DISABLE=1 arm-linux-gnueabihf-g++ -std=c++17 -Os -s -static \
    -o ubuntu/build_v3s/web_server \
    ubuntu/src/web_server.cpp /tmp/ws_o/*.o -lpthread 2>&1 | grep -iE 'error' | head -10
echo "web_server: $(ls -la ubuntu/build_v3s/web_server | awk '{print $5}') bytes"

echo "=== 编译 dji_rc (静态, SBUS/CRSF/回传) ==="
rm -rf /tmp/dji_o && mkdir -p /tmp/dji_o
for f in duml rc_decode chmap sbus crsf rc_map; do
    CCACHE_DISABLE=1 arm-linux-gnueabihf-gcc -O2 -s -c -o "/tmp/dji_o/${f}.o" "ubuntu/src/${f}.c"
done
CCACHE_DISABLE=1 arm-linux-gnueabihf-g++ -std=c++17 -O2 -s -static \
    -o ubuntu/build_v3s/dji_rc \
    ubuntu/src/dji_rc.cpp /tmp/dji_o/*.o -lpthread 2>&1 | grep -iE 'error' | head -10
echo "dji_rc: $(ls -la ubuntu/build_v3s/dji_rc | awk '{print $5}') bytes"

echo ""
echo "=== 二进制 md5 ==="
md5sum ubuntu/build_v3s/web_server ubuntu/build_v3s/dji_rc
echo "DONE"
