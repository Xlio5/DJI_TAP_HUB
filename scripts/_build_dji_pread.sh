#!/bin/bash
cd /mnt/c/my_project/TUN_NAT_HUB
rm -rf /tmp/dji_pp && mkdir -p /tmp/dji_pp
for f in duml rc_decode chmap sbus crsf rc_map; do
    CCACHE_DISABLE=1 arm-linux-gnueabihf-gcc -O2 -s -c -o "/tmp/dji_pp/${f}.o" "ubuntu/src/${f}.c" 2>&1 | head -3
done
CCACHE_DISABLE=1 arm-linux-gnueabihf-g++ -std=c++17 -O2 -s -Wall \
    -o ubuntu/build_v3s/dji_rc ubuntu/src/dji_rc.cpp /tmp/dji_pp/*.o -lpthread 2>&1 | grep -iE 'error' | head -10
echo "=== 结果 ==="
md5sum ubuntu/build_v3s/dji_rc 2>/dev/null
