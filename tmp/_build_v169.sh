#!/bin/bash
# _build_v169.sh — 交叉编译 dji_rc + web_server (v1.6.9, 400000 baud)
# 工具链: WSL Ubuntu-20.04 g++-arm-linux-gnueabihf 9.4.0 (glibc 2.31)
set -e
cd /mnt/c/work/tun_-nat_-hub
GCC=arm-linux-gnueabihf-gcc
GPP=arm-linux-gnueabihf-g++

echo "=== 编译 C 模块 ==="
for f in duml rc_decode chmap sbus rc_map crsf; do
  $GCC -O2 -s -c -o /tmp/${f}.o ubuntu/src/${f}.c || { echo "FAIL $f"; exit 1; }
done

echo "=== 编译 dji_rc (动态) ==="
$GPP -std=c++17 -O2 -s -Wall -o /tmp/dji_rc_v169 \
  ubuntu/src/dji_rc.cpp /tmp/duml.o /tmp/rc_decode.o /tmp/chmap.o /tmp/sbus.o /tmp/rc_map.o /tmp/crsf.o -lpthread

echo "=== 编译 web_server (静态) ==="
$GPP -std=c++17 -Os -s -static -Wall -o /tmp/web_server_v169 \
  ubuntu/src/web_server.cpp /tmp/rc_map.o /tmp/rc_decode.o /tmp/chmap.o -lpthread

echo "=== 验证 ==="
file /tmp/dji_rc_v169 /tmp/web_server_v169
ls -la /tmp/dji_rc_v169 /tmp/web_server_v169
