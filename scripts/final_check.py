"""Final V3s status check"""
import paramiko

ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
ssh.connect("192.168.144.66", username="root", password="root", timeout=5)

checks = [
    ("NAT", "iptables -t nat -L POSTROUTING -n 2>&1 | grep -E 'MASQ|10.0'"),
    ("GW", "ip route | grep default"),
    ("USB", "cat /sys/class/udc/*/state 2>&1"),
    ("daemon", "ps | grep usb_tund"),
    ("web", "ps | grep web_server"),
    ("rootfs", "mount | head -2"),
    ("MTD", "cat /proc/mtd"),
]

for label, cmd in checks:
    _, o, _ = ssh.exec_command(cmd, timeout=3)
    out = o.read().decode(errors="replace").strip()
    lines = out.split("\n")[:3]
    print(f"{label}:")
    for l in lines:
        print(f"  {l.strip()[:120]}")

ssh.close()
