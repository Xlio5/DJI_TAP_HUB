#!/bin/bash
# setup_gadget.sh — 加载 g_serial（纯 Bulk 模式）
set -e

# 已存在则跳过
if [ -c /dev/ttyGS0 ]; then
    echo "g_serial 已就绪 (/dev/ttyGS0)"
    exit 0
fi

echo "=== 加载 g_serial Gadget ==="

# 清理并重载
modprobe -r g_serial 2>/dev/null || true
sleep 1
modprobe g_serial use_acm=0 use_obex=0 idVendor=0x0BDA idProduct=0x8812
sleep 2

if [ -c /dev/ttyGS0 ]; then
    chmod 666 /dev/ttyGS0 2>/dev/null || true
    echo "g_serial 加载成功: /dev/ttyGS0"
else
    echo "警告: /dev/ttyGS0 未出现"
fi
