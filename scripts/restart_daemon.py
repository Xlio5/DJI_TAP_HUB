"""Restart daemon on RK3588."""
import paramiko
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("172.24.91.28", username="xlong", password="1234")

S = "echo '1234' | sudo -S"
for cmd in [
    "systemctl stop tun_nat_hub 2>/dev/null; echo stopped",
    "killall usb_tund 2>/dev/null; echo killed",
    "sleep 1",
    "cp /home/xlong/tun_nat_hub/ubuntu/build/usb_tund /usr/local/bin/usb_tund; echo copied",
    "systemctl restart tun_nat_hub; echo restarted",
    "sleep 2",
    "journalctl -u tun_nat_hub --no-pager -n 8",
]:
    stdin, stdout, stderr = c.exec_command(S + " bash -c '" + cmd + "'", timeout=15)
    out = stdout.read().decode(errors='replace')
    err = stderr.read().decode(errors='replace')
    if out.strip(): print(out.strip())
    if err.strip(): print("[e]", err.strip())

c.close()
print("Done")
