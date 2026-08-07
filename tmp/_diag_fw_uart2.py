"""诊断固化版 UART2 打开: 启动日志 + fd + ttyS2 状态"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

pid = "112"
print("=== 1. dji_rc fd (ttyS2 是否打开) ===")
print(r(f"ls -la /proc/{pid}/fd/ 2>/dev/null | grep -E 'ttyS'"))
print("\n=== 2. 启动日志头 20 行 (UART2 打开) ===")
print(r("head -20 /var/log/dji_rc.log 2>/dev/null"))
print("\n=== 3. ttyS2 设备状态 ===")
print(r("ls -la /dev/ttyS2; stty -F /dev/ttyS2 2>&1 | head -3 || echo 'stty 失败'"))
print("\n=== 4. 内核 ttyS2 注册 ===")
print(r("cat /proc/tty/driver/serial 2>/dev/null || echo 无"))
print("\n=== 5. UART2 引脚/时钟 (devmem) ===")
print(r("devmem 0x01C20800 32 2>/dev/null; echo '---'; cat /sys/kernel/debug/uart* 2>/dev/null | head -3 || echo '无 debug'"))
c.close()
print("\n[done]")
