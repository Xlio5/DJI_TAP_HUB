"""抓 g1/g2 准确计数 + 两路 UART 状态"""
import paramiko, time, re

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

# 用 awk 取日志最后一条的 g1/g2
print("=== 1. 日志最后一条 (完整) ===")
line = r("tail -1 /var/log/dji_rc.log")
print(line[:200])
m = re.search(r'g1=(\d+) g2=(\d+)', line)
if m:
    print(f"\ng1(UART1)={m.group(1)}  g2(UART2)={m.group(2)}")

print("\n=== 2. 20 秒后 ===")
time.sleep(20)
line2 = r("tail -1 /var/log/dji_rc.log")
m2 = re.search(r'g1=(\d+) g2=(\d+)', line2)
if m2:
    print(f"g1={m2.group(1)}  g2={m2.group(2)}")
    print(f"UART1 20s 增长: {int(m2.group(1))-int(m.group(1))}")
    print(f"UART2 20s 增长: {int(m2.group(2))-int(m.group(2))}")

print("\n=== 3. 状态文件 type + last_us ===")
print(r("grep -oE '\"type\":\"[^\"]*\"|\"good1\":[0-9]*|\"good2\":[0-9]*' /var/log/rc_state.json | head -5"))
c.close()
print("\n[done]")
