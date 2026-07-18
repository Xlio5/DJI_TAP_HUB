#!/bin/sh
# V3s 纯 SPI 启动 — 全系统健康检查
echo "============================================"
echo "  V3s SPI Boot Health Check"
echo "============================================"
echo ""

# 1. 内核启动
echo "=== 1. Uptime / Kernel ==="
cat /proc/version
echo "Uptime: $(cat /proc/uptime | awk '{print $1}')s"
echo ""

# 2. 根文件系统
echo "=== 2. Root filesystem ==="
mount | grep " / "
echo "Root type: $(stat -f / --format=%T)"
echo ""

# 3. SPI Flash 分区
echo "=== 3. SPI Flash (MTD) ==="
cat /proc/mtd 2>/dev/null || echo "No /proc/mtd"
echo ""

# 4. g_serial USB
echo "=== 4. g_serial ==="
gadget_dir=$(find /sys/kernel/config/usb_gadget -name "g_serial" -type d 2>/dev/null | head -1)
if [ -z "$gadget_dir" ]; then
  echo "  UDC: $(cat /sys/class/udc/*/state 2>/dev/null || echo 'checking...')"
else
  echo "  ConfigFS gadget found"
fi
echo "  ttyGS0: $(test -c /dev/ttyGS0 && echo 'EXISTS' || echo 'MISSING')"
echo ""

# 5. TUN interface
echo "=== 5. TUN ==="
ip link show tun_hub 2>/dev/null && echo "  tun_hub: UP" || echo "  tun_hub: NOT FOUND"
ip addr show eth0 2>/dev/null | grep "inet " && echo "  eth0: has IP" || echo "  eth0: no IP yet (waiting DHCP)"
echo ""

# 6. Running services
echo "=== 6. Services ==="
echo "  usb_tund:   $(pgrep usb_tund >/dev/null && echo 'RUNNING' || echo 'DOWN')"
echo "  web_server: $(pgrep web_server >/dev/null && echo 'RUNNING' || echo 'DOWN')"
echo "  dropbear:   $(pgrep dropbear >/dev/null && echo 'RUNNING' || echo 'DOWN')"
echo ""

# 7. IP forwarding
echo "=== 7. NAT ==="
echo "  ip_forward: $(cat /proc/sys/net/ipv4/ip_forward 2>/dev/null)"
echo "  MASQUERADE: $(iptables -t nat -L POSTROUTING -n 2>/dev/null | grep MASQUERADE | head -1 || echo 'not yet')"
echo ""

# 8. Web panel
echo "=== 8. web_server ==="
if pgrep web_server > /dev/null; then
  echo "  HTTP test:"
  curl -s -o /dev/null -w "  HTTP code: %{http_code}\n" http://127.0.0.1:8080/api/heartbeat 2>/dev/null || echo "  curl failed (normal - may not be installed)"
else
  echo "  web_server not running"
fi
echo ""

# 9. Memory
echo "=== 9. Memory ==="
free -m 2>/dev/null || (echo "  MemTotal: $(grep MemTotal /proc/meminfo 2>/dev/null | awk '{print $2}') KB")
echo ""

# 10. Booting from
echo "=== 10. Boot source ==="
echo "  Kernel cmdline: $(cat /proc/cmdline 2>/dev/null)"
echo ""

echo "============================================"
echo "  CHECK COMPLETE"
echo "============================================"
