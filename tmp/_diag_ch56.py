"""诊断 CH5/CH6 串口交叉: 抓当前两路 UART 解码 + 状态"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("=== 1. dji_rc 进程 + 参数 ===")
print(r("ps w | grep dji_rc | grep -v grep | head -1"))
print("\n=== 2. 日志头 25 行 (启动 + selftest 通道) ===")
print(r("head -25 /var/log/dji_rc.log 2>/dev/null"))
print("\n=== 3. 当前 CH 行 (最近 3 条) ===")
print(r("grep 'CH1=' /var/log/dji_rc.log 2>/dev/null | tail -3"))
print("\n=== 4. rc_state.json (web_server 状态) ===")
print(r("cat /var/log/rc_state.json 2>/dev/null | head -c 500"))
print("\n=== 5. 两个串口 rx 字节数 (dmesg?) ===")
print(r("dmesg 2>/dev/null | grep -iE 'ttyS|uart' | tail -5 || echo 无"))
c.close()
print("\n[done]")
