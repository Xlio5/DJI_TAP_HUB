"""同时抓取 ttyS1 (P20/摇杆) 和 ttyS2 (P0/按键) 实时数据, 对比两个串口状态
方案: 后台并行 dd 抓两个串口 3 秒, 同时记录 dji_rc rx 计数变化
"""
import paramiko, time

def ssh_connect(host, user, pw, retries=6, timeout=12):
    for i in range(retries):
        try:
            c = paramiko.SSHClient()
            c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            c.connect(host, 22, user, pw, timeout=timeout, allow_agent=False,
                      look_for_keys=False, banner_timeout=timeout, auth_timeout=timeout)
            return c
        except Exception as e:
            print(f"  [重试{i+1}] {e}")
            time.sleep(3)
    return None

c = ssh_connect("192.168.144.66", "root", "root")
if not c:
    print("V3s SSH 失败"); exit(1)

def r(cmd, wait=0.5):
    _, out, err = c.exec_command(cmd)
    time.sleep(wait)
    return (out.read() + err.read()).decode(errors="replace").strip()

print("=== 1. 当前 rc_state.json (rx1/rx2/good) ===")
print(r("cat /var/log/rc_state.json 2>/dev/null | head -1 || echo no-state"))

print("=== 2. 同时抓 ttyS1 和 ttyS2 各 3 秒 ===")
r("killall dd 2>/dev/null; rm -f /tmp/s1.raw /tmp/s2.raw")
# 用 grep 方式直接读串口原始字节 (不改变 termios)
r("(dd if=/dev/ttyS1 bs=1 count=10000 of=/tmp/s1.raw 2>/dev/null) & S1=$!")
r("(dd if=/dev/ttyS2 bs=1 count=10000 of=/tmp/s2.raw 2>/dev/null) & S2=$!")
time.sleep(3)
r("kill %1 %2 2>/dev/null")
r("pkill -9 dd 2>/dev/null; sleep 0.5")

print(r("echo 'ttyS1 抓到:'; stat -c '%s bytes' /tmp/s1.raw 2>/dev/null || echo '0'"))
print(r("echo 'ttyS2 抓到:'; stat -c '%s bytes' /tmp/s2.raw 2>/dev/null || echo '0'"))

print("=== 3. 两个串口的字节内容 (前 60 字节) ===")
print("--- ttyS1 (921600 摇杆) ---")
print(r("xxd /tmp/s1.raw 2>/dev/null | head -10 || echo empty"))
print("--- ttyS2 (115200 按键) ---")
print(r("xxd /tmp/s2.raw 2>/dev/null | head -10 || echo empty"))

print("=== 4. 抓取后 rc_state.json (rx 是否变化) ===")
print(r("cat /var/log/rc_state.json 2>/dev/null | head -1 || echo no-state"))

print("=== 5. dji_rc 是否还活着 ===")
print(r("ps w | grep dji_rc | grep -v grep || echo DEAD"))

c.close()
print("\n[done]")
