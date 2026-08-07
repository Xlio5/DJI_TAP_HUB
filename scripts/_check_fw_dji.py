"""检查当前固件 dji_rc 版本 + 需不需要 OTA"""
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

print("=== 1. 系统 dji_rc md5 (固化版) ===")
print(ssh_r("md5sum /usr/local/bin/dji_rc"))
print("  修复版: dbedf0c8")
print("\n=== 2. 运行中 dji_rc ===")
print(ssh_r("ps w | grep dji_rc | grep -v grep | head -2"))
c.close()
print("\n[done]")
