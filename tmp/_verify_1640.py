"""验证 v1.6.40: 等心跳恢复 + PIO 0x28 + 进程 + COM10 login"""
import time, urllib.request, json, paramiko, serial

# 1. 等 heartbeat 恢复 (最多 75s)
print("=== 等待设备心跳恢复 ===")
hb = None
for i in range(30):
    try:
        with urllib.request.urlopen("http://192.168.144.66:8080/api/heartbeat", timeout=2) as r:
            hb = json.loads(r.read().decode())
            break
    except Exception:
        time.sleep(2.5)
if hb:
    print(f"✅ heartbeat: version={hb.get('version')} uptime={hb.get('uptime_since')}")
else:
    print("❌ 设备 75s 内未恢复心跳")
    raise SystemExit(1)

# 2. SSH 检查 PIO + 进程
print("\n=== SSH 检查 PIO 0x28 (PB8/PB9) + 进程 ===")
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=10,
          allow_agent=False, look_for_keys=False, banner_timeout=10)
def sh(cmd):
    i, o, e = c.exec_command(cmd, timeout=8)
    return o.read().decode("utf-8", "replace")
print("PB_CFG1@0x28:", sh("devmem 0x01C20828 32").strip())
print("PB_CFG0@0x24:", sh("devmem 0x01C20824 32").strip())
print("PB_DATA@0x34:", sh("devmem 0x01C20834 32").strip())
print("进程:", sh("ps w | grep -E '[g]etty|[d]ji_rc'").strip())
print("getty fd:", sh("G=$(pidof getty); ls -la /proc/$G/fd 2>/dev/null | grep tty").strip())
c.close()

# 3. COM10 发回车触发 login
print("\n=== COM10 发回车触发 getty login ===")
s = serial.Serial("COM10", 115200, timeout=0.3)
time.sleep(0.3)
s.reset_input_buffer()
s.write(b"\r\n")
buf = b""
end = time.time() + 3
while time.time() < end:
    d = s.read(1024)
    if d: buf += d
s.write(b"\r\n")
end = time.time() + 2
while time.time() < end:
    d = s.read(1024)
    if d: buf += d
s.close()
print("COM10 收到:", repr(buf[:300]))
if b"login" in buf.lower() or b"welcome" in buf.lower() or b"password" in buf.lower():
    print("✅ UART0 debug getty 正常工作 (login 提示出现)")
else:
    print("❌ COM10 无 login 响应")
