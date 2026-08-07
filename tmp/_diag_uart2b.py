"""诊断 UART2: 原始数据流 + dji_rc 状态 + 融合"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=2.0):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("=== 1. dji_rc 进程 ===")
print(r("ps w | grep dji_rc | grep -v grep | head -1 || echo 无"))

print("\n=== 2. 状态文件完整内容 ===")
print(r("cat /var/log/rc_state.json 2>/dev/null | head -c 800"))

print("\n=== 3. UART2 原始数据 (ttyS2, 100字节) ===")
print(r("timeout 3 dd if=/dev/ttyS2 bs=1 count=100 2>/dev/null | hexdump -C | head -8 || echo '读不到'"))

print("\n=== 4. UART1 原始数据 (ttyS1, 100字节) ===")
print(r("timeout 3 dd if=/dev/ttyS1 bs=1 count=100 2>/dev/null | hexdump -C | head -8 || echo '读不到'"))

print("\n=== 5. 日志里 SPECIAL 解码详情 ===")
print(r("grep -iE 'SPECIAL|0x02|decode' /var/log/dji_rc.log | head -10"))
c.close()
print("\n[done]")
