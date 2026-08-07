"""用 v150 旧 dji_rc 测试 UART2 是否恢复 (定位固化版问题)"""
import paramiko, time, base64

V3S = "192.168.144.66"
# 从 rootfs_v150 提取 dji_rc (fad8b8f2)
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(V3S, 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=2.0, stdin_data=None):
    stdin, out, err = c.exec_command(cmd)
    if stdin_data is not None:
        stdin.write(stdin_data)
        stdin.channel.shutdown_write()
    time.sleep(wait)
    return (out.read() + err.read()).decode(errors="replace").strip()

# 从当前 rootfs (固化版) 无法直接拿 v150。先看本机 backup/rootfs_v150 提取
print("=== 从本机 rootfs_v150 提取 dji_rc ===")
import subprocess, os
# 用 WSL unsquashfs 提取
subprocess.run(["wsl", "-d", "Ubuntu-20.04", "--", "bash", "-c",
    "rm -rf /tmp/v150x && unsquashfs -q -d /tmp/v150x /mnt/c/my_project/TUN_NAT_HUB/backup/rootfs_v150.squashfs && "
    "cp /tmp/v150x/usr/local/bin/dji_rc /mnt/c/my_project/TUN_NAT_HUB/tmp/dji_rc_v150 && "
    "md5sum /mnt/c/my_project/TUN_NAT_HUB/tmp/dji_rc_v150"], check=True)

# 传输到设备
data = open(r"c:\my_project\TUN_NAT_HUB\tmp\dji_rc_v150", "rb").read()
b64 = base64.b64encode(data).decode()
print("v150 dji_rc 大小:", len(data))
print(r("base64 -d > /tmp/dji_rc_v150 && chmod +x /tmp/dji_rc_v150 && md5sum /tmp/dji_rc_v150", wait=3.0, stdin_data=b64))

# 停固化版, 跑 v150
print("\n停固化版:", r("killall dji_rc 2>/dev/null; sleep 1; echo ok"))
print("跑 v150:", r("/tmp/dji_rc_v150 --interval 20 --out-dev /dev/ttyS0 --out-baud auto --crsf-telem 1 --rcmsg-host 10.0.0.2 --rcmsg-port 65530 > /var/log/dji_rc_v150.log 2>&1 & echo PID=$!"))
time.sleep(10)
print("\nrx1/rx2 (v150):", r("grep 'CH1=' /var/log/dji_rc_v150.log | tail -1 | grep -oE 'rx1=[0-9]* rx2=[0-9]*'"))
print("g1/g2:", r("grep 'CH1=' /var/log/dji_rc_v150.log | tail -1 | grep -oE 'g1=[0-9]* g2=[0-9]*'"))
print("fd:", r("ls -la /proc/$(ls /proc | grep -E '^[0-9]+$' | while read p; do grep -q dji_rc /proc/$p/cmdline 2>/dev/null && echo $p && break; done)/fd/ 2>/dev/null | grep ttyS"))
c.close()
print("\n[done]")
