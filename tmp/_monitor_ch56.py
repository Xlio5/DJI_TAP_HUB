"""实时监控 CH5/CH6 跳动: 采样 dji_rc 日志 + rc_state.json"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("=== 采样 20 次 (每 1s), 看 CH5/CH6 是否跳动 ===")
for i in range(20):
    line = r("grep 'CH1=' /var/log/dji_rc.log 2>/dev/null | tail -1")
    # 提取 CH5/CH6
    import re
    m = re.search(r'CH5=([+-]?\d+) CH6=([+-]?\d+)', line)
    rx = re.search(r'rx1=(\d+) rx2=(\d+)', line)
    if m:
        print(f"[{i}] CH5={m.group(1)} CH6={m.group(2)}" + (f" rx1={rx.group(1)} rx2={rx.group(2)}" if rx else ""))
    time.sleep(1)
print("\n=== 状态文件 raw_ch5/raw_ch6 ===")
print(r("cat /var/log/rc_state.json 2>/dev/null | python3 -c 'import sys,json; d=json.load(sys.stdin); print(\"raw_ch5:\",d.get(\"raw_ch5\"),\"raw_ch6:\",d.get(\"raw_ch6\"),\"ch5:\",d.get(\"ch5\"),\"ch6:\",d.get(\"ch6\"))' 2>/dev/null || grep -o '\"raw_ch5\":[0-9-]*,\"raw_ch6\":[0-9-]*' /var/log/rc_state.json"))
c.close()
print("\n[done]")
