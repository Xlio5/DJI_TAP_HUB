# -*- coding: utf-8 -*-
"""V3s 应用做法B: 手机 144.11, 砍 10.0.0.x"""
import subprocess, sys

PLINK = r"C:\Program Files\PuTTY\plink.exe"
HOST = "192.168.144.66"

probe = subprocess.run([PLINK, "-batch", "-pw", "root", f"root@{HOST}", "echo x"],
                       capture_output=True, text=True, errors='replace')
FP = [l for l in probe.stderr.splitlines() if "SHA256:" in l][0].split()[-1]

def ssh(cmd, t=25):
    r = subprocess.run([PLINK, "-batch", "-hostkey", FP, "-pw", "root", f"root@{HOST}", cmd],
                       capture_output=True, text=True, errors='replace', timeout=t)
    return r.stdout.strip(), r.stderr.strip()

# 清旧配置 (10.0.0.x / 144.200 / 14550 DNAT / MASQUERADE)
cmds = [
    "ip addr del 10.0.0.1/24 dev tun_hub 2>/dev/null",
    "ip route del 10.0.0.0/24 dev tun_hub 2>/dev/null",
    "ip route del 192.168.144.200/32 dev tun_hub 2>/dev/null",
    "iptables -t nat -D PREROUTING -i eth0 -p udp --dport 14550 -j DNAT --to-destination 10.0.0.2:14550 2>/dev/null",
    "iptables -t nat -D PREROUTING -i eth0 -p udp --dport 14550 -j DNAT --to-destination 10.0.0.2:65532 2>/dev/null",
    "iptables -D FORWARD -i eth0 -o tun_hub -d 192.168.144.200 -j ACCEPT 2>/dev/null",
    "iptables -D FORWARD -i eth0 -o tun_hub -p udp --dport 14550 -j ACCEPT 2>/dev/null",
    "iptables -t nat -D POSTROUTING -s 10.0.0.0/24 -o eth0 -j MASQUERADE 2>/dev/null",
    "iptables -t nat -D POSTROUTING -s 192.168.144.0/24 -o eth0 -j MASQUERADE 2>/dev/null",
]
for c in cmds:
    ssh(c)
print("旧配置已清")

# 新配置: 手机 144.11
new = [
    "ip route add 192.168.144.11/32 dev tun_hub 2>/dev/null",
    "echo 1 > /proc/sys/net/ipv4/conf/eth0/proxy_arp",
    "iptables -A FORWARD -i eth0 -o tun_hub -d 192.168.144.11 -j ACCEPT 2>/dev/null",
    "iptables -A FORWARD -i tun_hub -o eth0 -j ACCEPT 2>/dev/null",
    "iptables -A FORWARD -i eth0 -o tun_hub -m state --state ESTABLISHED,RELATED -j ACCEPT 2>/dev/null",
]
for c in new:
    ssh(c)
print("新配置已加")

# 验证
out, _ = ssh("ip route; echo PROXY; cat /proc/sys/net/ipv4/conf/eth0/proxy_arp; echo FWD; iptables -L FORWARD -n | grep 144.11; echo TUN; ip addr show tun_hub")
print(out)
