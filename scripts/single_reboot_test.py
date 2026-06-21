"""Single reboot test — reboot, wait, verify."""
import paramiko, base64, time, os

WIRED = "192.168.88.66"
WIFI = "172.24.91.129"

# 1. Connect and setup crontab + upload
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(WIRED, username="xlong", password="1234", timeout=10)

# Upload fix script
with open(r"c:\my_project\TUN_NAT_HUB\scripts\cold_boot_fix.sh", "rb") as f:
    data = f.read().replace(b"\r\n", b"\n")
b64 = base64.b64encode(data).decode()
ch = c.get_transport().open_session()
ch.exec_command("base64 -d > /home/xlong/cold_boot_fix.sh")
ch.sendall(b64.encode())
ch.shutdown_write()
ch.recv_exit_status()
ch.close()
stdin, stdout, stderr = c.exec_command("chmod +x /home/xlong/cold_boot_fix.sh")
stdout.read()

# Add @reboot cron
cron_cmd = '(crontab -l 2>/dev/null; echo "@reboot sleep 20 && bash /home/xlong/cold_boot_fix.sh >> /home/xlong/boot_fix.log 2>&1") | crontab -'
stdin, stdout, stderr = c.exec_command("echo 1234 | sudo -S bash -c '" + cron_cmd + "'", timeout=5)
stdout.read()
print("Crontab set")

# Verify crontab
stdin, stdout, stderr = c.exec_command("crontab -l 2>&1 | grep cold_boot")
print("Cron:", stdout.read().decode(errors="replace").strip())

# Reboot
stdin, stdout, stderr = c.exec_command("echo 1234 | sudo -S reboot 2>/dev/null &", timeout=3)
stdout.read()
c.close()
print("Rebooting...")

# Wait
for i in range(90, 0, -10):
    time.sleep(10)
    print("  {}s...".format(i))
print()

# Reconnect and verify
ok = False
for ip in [WIRED, WIFI]:
    try:
        c2 = paramiko.SSHClient()
        c2.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        c2.connect(ip, username="xlong", password="1234", timeout=10)
        print("SSH: {}".format(ip))

        # Check crontab output
        stdin, stdout, stderr = c2.exec_command(
            "cat /home/xlong/boot_fix.log 2>&1 | tail -5", timeout=5)
        log = stdout.read().decode(errors="replace").strip()
        print("Crontab log: {}".format(log[:400]))

        # Run fix again manually
        stdin, stdout, stderr = c2.exec_command(
            "echo 1234 | sudo -S bash /home/xlong/cold_boot_fix.sh",
            timeout=30, get_pty=True)
        out = b""
        t0 = time.time()
        while time.time() - t0 < 25:
            if stdout.channel.recv_ready():
                out += stdout.channel.recv(4096)
            if stdout.channel.exit_status_ready():
                break
            time.sleep(0.2)
        try: out += stdout.read()
        except: pass
        print(out.decode(errors="replace"))

        c2.close()
        ok = "ALL_OK" in out.decode(errors="replace")
        break
    except Exception as e:
        print("{}: {}".format(ip, e))

if ok:
    print("ROUND 2: ALL OK")
else:
    print("ROUND 2: STILL BROKEN")
