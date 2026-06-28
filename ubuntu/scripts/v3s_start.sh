#!/bin/sh
# TUN_NAT_HUB V3s 启动脚本
echo '=== TUN_NAT_HUB V3s Starting ==='

# Kill old instances
killall usb_tund 2>/dev/null
killall python3 2>/dev/null
sleep 1

# Start daemon
/usr/local/bin/usb_tund > /var/log/usb_tund.log 2>&1 &
echo "usb_tund: PID=$!"

# Start web panel
python3 /usr/local/bin/web_panel.py > /var/log/web_panel.log 2>&1 &
echo "web_panel: PID=$!"

sleep 2

# Verify
echo '--- Processes ---'
ps | grep -E 'usb_tund|web_panel' | grep -v grep
echo '--- TUN ---'
ip addr show tun_hub | grep inet
echo '--- Web API ---'
wget -q -O - http://127.0.0.1:8080/api/heartbeat 2>&1
echo ''
echo '=== DONE ==='
