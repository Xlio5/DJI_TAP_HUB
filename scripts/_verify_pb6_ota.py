"""验证 OTA 后: 修复版 dji_rc + PB6 上拉协议模式"""
import paramiko, time

V3S = "192.168.144.66"

def ssh_r(cmd, wait=2.0):
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(V3S, 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)
    _, out, err = c.exec_command(cmd)
    time.sleep(wait)
    r = (out.read() + err.read()).decode(errors="replace").strip()
    c.close()
    return r

print("=== 1. 分区 + dji_rc md5 ===")
print(ssh_r("cat /proc/cmdline | grep -o 'root=[^ ]*'"))
print(ssh_r("md5sum /usr/local/bin/dji_rc"))
print("  期望: dbedf0c8 (修复版)")
print("\n=== 2. PB6 检测 (上拉=协议) ===")
print(ssh_r("grep -E 'PB6|输出 /|debug|协议' /var/log/dji_rc.log | head -8"))
print("\n=== 3. getty (协议模式应无) ===")
print(ssh_r("ps w | grep getty | grep -v grep || echo '无 getty (协议模式正确)'"))
print("\n=== 4. 服务 ===")
print(ssh_r("ps w | grep -E 'web_server|dji_rc|usb_tund' | grep -v grep | awk '{print $1, $5}'"))
print("\n=== 5. web ===")
print(ssh_r("wget -q -O - --timeout=3 http://127.0.0.1:8080/api/version 2>&1"))
c.close()
print("\n[done]")
