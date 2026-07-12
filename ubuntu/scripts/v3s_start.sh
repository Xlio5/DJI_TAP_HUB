#!/bin/sh
# TUN_NAT_HUB V3s 启动脚本
set -e
echo '=== TUN_NAT_HUB V3s Starting ==='

# Kill old instances (只杀 usb_tund + web_server)
killall usb_tund web_server 2>/dev/null || true
sleep 1

# Start daemon
/usr/local/bin/usb_tund > /var/log/usb_tund.log 2>&1 &
echo "usb_tund: PID=$!"

# Start web panel (C++ 嵌入式)
/usr/local/bin/web_server > /var/log/web_server.log 2>&1 &
echo "web_server: PID=$!"

sleep 2

# Verify
echo '--- Processes ---'
ps aux 2>/dev/null | grep '[u]sb_tund\|[w]eb_panel' || true
echo '--- TUN ---'
ip addr show tun_hub 2>/dev/null | grep inet || true
echo '--- Web API ---'
wget -q -O - http://127.0.0.1:8080/api/heartbeat 2>/dev/null || echo "WARNING: API check failed"
echo ''
echo '=== DONE ==='
