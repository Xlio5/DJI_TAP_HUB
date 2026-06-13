#!/bin/bash
# setup_gadget.sh — 加载 ECM/RNDIS Ethernet Gadget
# 优先 ECM (g_ether)，失败时回退 RNDIS (g_rndis)
# 替换原 g_serial (use_acm=0) 方案，绕过 DJI RC USB 白名单限制
set -e

GADGET_IFACE="usb0"

# 已存在则跳过
if ip link show "$GADGET_IFACE" &>/dev/null; then
    echo "ECM/RNDIS 已就绪 ($GADGET_IFACE)"
    exit 0
fi

echo "=== 加载 ECM/RNDIS Gadget ==="

# 清理所有旧模块（g_serial, g_ether, g_rndis）
for mod in g_ether g_rndis g_serial; do
    modprobe -r "$mod" 2>/dev/null || true
done
sleep 1

# 优先尝试 ECM (标准 CDC-ECM，不会从 Linux 内核废弃)
echo "尝试加载 g_ether (ECM)..."
modprobe g_ether dev_addr=02:00:00:00:00:01 host_addr=02:00:00:00:00:02
sleep 3

if ip link show "$GADGET_IFACE" &>/dev/null; then
    # 配置静态 IP
    ip addr replace 10.0.0.1/24 dev "$GADGET_IFACE"
    ip link set "$GADGET_IFACE" up
    echo "ECM 加载成功: $GADGET_IFACE (10.0.0.1/24)"
    exit 0
fi

# 回退到 RNDIS（Android 默认 USB tethering 模式）
echo "ECM 未识别，尝试 RNDIS 回退..."
modprobe -r g_ether 2>/dev/null || true
sleep 1

modprobe g_rndis dev_addr=02:00:00:00:00:01 host_addr=02:00:00:00:00:02
sleep 3

if ip link show "$GADGET_IFACE" &>/dev/null; then
    ip addr replace 10.0.0.1/24 dev "$GADGET_IFACE"
    ip link set "$GADGET_IFACE" up
    echo "RNDIS 加载成功: $GADGET_IFACE (10.0.0.1/24)"
    exit 0
fi

# 尝试备选接口名 (Android 可能命名为 usb1, rndis0 等)
for fallback in usb1 rndis0; do
    if ip link show "$fallback" &>/dev/null; then
        ip addr replace 10.0.0.1/24 dev "$fallback"
        ip link set "$fallback" up
        echo "备选接口就绪: $fallback (10.0.0.1/24)"
        exit 0
    fi
done

echo "错误: ECM/RNDIS Gadget 加载失败，未找到 usb0/rndis0 接口"
exit 1
