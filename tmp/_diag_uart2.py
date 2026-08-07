"""诊断 UART2 通道融合: 对比两路 UART 实时解码状态"""
import paramiko, time, re

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("=== 1. 两路 UART 解码计数 (g1=UART1, g2=UART2) 20 秒变化 ===")
s1 = r("grep 'CH1=' /var/log/dji_rc.log | tail -1")
m1 = re.search(r'g1=(\d+) g2=(\d+)', s1)
print(f"起始: g1={m1.group(1)} g2={m1.group(2)}" if m1 else "无")
time.sleep(20)
s2 = r("grep 'CH1=' /var/log/dji_rc.log | tail -1")
m2 = re.search(r'g1=(\d+) g2=(\d+)', s2)
print(f"20秒后: g1={m2.group(1)} g2={m2.group(2)}" if m2 else "无")

print("\n=== 2. 当前输出 type (融合结果来自哪路) ===")
print(r("grep -o '\"type\":\"[A-Z/0-9]*\"' /var/log/rc_state.json 2>/dev/null | head -1"))
print(r("grep 'CH1=' /var/log/dji_rc.log | tail -1 | grep -oE 'MODE=.' | head -1"))

print("\n=== 3. UART2 (SPECIAL) 是否有独立解码记录 ===")
print(r("grep -iE 'SPECIAL|0x02' /var/log/dji_rc.log | tail -5"))

print("\n=== 4. 当前 raw_ch 值 ===")
print(r("cat /var/log/rc_state.json 2>/dev/null | grep -o '\"raw_ch[0-9]\":[0-9-]*'"))
c.close()
print("\n[done]")
