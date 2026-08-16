#!/bin/bash
# 编译 usb_tund (tun_hub 自配置修复)
set -e
cd /mnt/c/my_project/TUN_NAT_HUB
echo "=== 编译 usb_tund ==="
arm-linux-gnueabihf-g++ -std=c++17 -O2 -s -Iprotocol \
    -o ubuntu/build_v3s/usb_tund \
    ubuntu/src/main.cpp ubuntu/src/heartbeat.cpp ubuntu/src/tun_iface.cpp ubuntu/src/usb_gadget.cpp \
    -lpthread 2>&1 | grep -iE 'error|warning' | head -10 || true
echo "=== 结果 ==="
if [ -f ubuntu/build_v3s/usb_tund ]; then
    ls -la ubuntu/build_v3s/usb_tund
    md5sum ubuntu/build_v3s/usb_tund
else
    echo "编译失败!"
fi
