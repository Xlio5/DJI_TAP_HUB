#!/bin/bash
# setup_gadget.sh — 使用 g_serial (纯 Bulk 模式) 创建 USB Gadget
# 由 systemd ExecStartPre 调用。udev 规则备选方案。

set -e

# 如果 ttyGS0 已存在，跳过
if [ -c /dev/ttyGS0 ]; then
    echo "g_serial 已就绪 (/dev/ttyGS0)"
    exit 0
fi

echo "=== 加载 g_serial Gadget ==="

# 清理可能冲突的旧 gadget
for g in /sys/kernel/config/usb_gadget/*/UDC; do
    [ -f "$g" ] && echo "" > "$g" 2>/dev/null || true
done

modprobe -r g_serial 2>/dev/null || true

# 加载 g_serial — 纯 Bulk 模式
# use_acm=0: 非 CDC ACM，免握手
# use_obex=0: 不用 OBEX
modprobe g_serial use_acm=0 use_obex=0 idVendor=0x2207 idProduct=0x0010

# 给 udev 一点时间创建设备节点
sleep 1

if [ -c /dev/ttyGS0 ]; then
    echo "g_serial 加载成功: /dev/ttyGS0"
    # 允许 dialout 组读写
    chmod 660 /dev/ttyGS0 2>/dev/null || true
else
    echo "警告: /dev/ttyGS0 未出现"
fi
