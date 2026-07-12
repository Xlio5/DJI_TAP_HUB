#!/usr/bin/env python3
"""删除 Python3，写新版 S99 启动脚本，验证"""
import paramiko, time

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("192.168.144.66", username="root", password="root", timeout=10)

# 1. Check disk usage before
_, o, _ = ssh.exec_command("df -h / | tail -1")
print("Before:", o.read().decode().strip())

# 2. Delete python3
_, o, e = ssh.exec_command("rm -rf /usr/lib/python3.11 /usr/bin/python* /usr/bin/pydoc* 2>/dev/null; echo RM_OK")
print(o.read().decode().strip())

# 3. Disk after
_, o, _ = ssh.exec_command("df -h / | tail -1")
print("After:", o.read().decode().strip())

# 4. Write new S99 script
script = r"""#!/bin/sh
set -e
MODE_SYSFS="/sys/devices/platform/soc/1c19000.usb/musb-hdrc.2.auto/mode"
case "$1" in
  start)
    echo "Starting TUN_NAT_HUB..."
    /usr/local/bin/usb_tund > /var/log/usb_tund.log 2>&1 &
    echo "daemon: started"
    /usr/local/bin/setup_v3s.sh
    /usr/local/bin/web_server > /var/log/web_server.log 2>&1 &
    echo "web_server: started"
    echo peripheral > "$MODE_SYSFS" 2>/dev/null || true
    sleep 1
    echo host > "$MODE_SYSFS" 2>/dev/null || true
    sleep 5
    echo peripheral > "$MODE_SYSFS" 2>/dev/null || true
    sleep 1
    [ -c /dev/ttyGS0 ] && chmod 666 /dev/ttyGS0
    echo "TUN_NAT_HUB started"
    ;;
  stop)
    echo "Stopping TUN_NAT_HUB..."
    killall usb_tund web_server 2>/dev/null || true
    ;;
  restart)
    $0 stop; sleep 1; $0 start
    ;;
  *)
    echo "Usage: $0 {start|stop|restart}"
    ;;
esac
"""

# Use exec_command to write via cat
chan = ssh.get_transport().open_session()
chan.exec_command("cat > /etc/init.d/S99tun_nat_hub && chmod +x /etc/init.d/S99tun_nat_hub && echo INIT_OK")
time.sleep(0.3)
chan.sendall(script.encode())
chan.shutdown_write()
time.sleep(1)
out = chan.recv(4096).decode()
print("Init:", out.strip())

# 5. Verify
_, o, _ = ssh.exec_command("ls -la /etc/init.d/S99tun_nat_hub; echo ===; head -5 /etc/init.d/S99tun_nat_hub")
print(o.read().decode())

# 6. Clean up temp files
_, o, _ = ssh.exec_command("rm -f /tmp/ws_* /tmp/ws_b64 /tmp/ws_new 2>/dev/null; echo CLEANED")
print(o.read().decode().strip())

ssh.close()
print("Done! Restart V3s to verify auto-start.")
