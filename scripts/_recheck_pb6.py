"""重新跑 dji_rc 看当前 PB6 检测 (接地状态)"""
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

print("=== 1. devmem 当前 DATA (接地=0) ===")
print("DATA 0x34:", ssh_r("devmem 0x01C20834 2>/dev/null"))

print("\n=== 2. 杀 dji_rc, 手动跑看检测 ===")
print(ssh_r("killall dji_rc 2>/dev/null; sleep 1; (/usr/local/bin/dji_rc --interval 20 --out-dev /dev/ttyS0 --out-baud auto --crsf-telem 1 --rcmsg-host 10.0.0.2 --rcmsg-port 65530 > /tmp/dji_test.log 2>&1 &); sleep 4; grep -E 'PB6 检测|接地|debug 模式|协议|输出 /dev' /tmp/dji_test.log | head -8"))

print("\n=== 3. 当前 dji_rc 是否切到 debug (无 out) ===")
print(ssh_r("grep -E 'out ok|no-RC|CH1=' /tmp/dji_test.log | tail -3"))
c.close()
print("\n[done]")
