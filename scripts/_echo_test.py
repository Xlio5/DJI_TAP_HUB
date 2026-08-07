import paramiko, time, os

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False, banner_timeout=10)

def r(cmd):
    _, out, _ = c.exec_command(cmd); time.sleep(0.5)
    return out.read().decode(errors="replace")

# Step 1: Kill existing
r("killall dji_rc uart_echo 2>/dev/null; sleep 0.3")

# Step 2: Upload via sftp
print("uploading...")
sftp = c.open_sftp()
sftp.put(r"c:\my_project\TUN_NAT_HUB\scripts\uart_echo", "/var/log/uart_echo")
sftp.close()
print("upload OK, size=" + r("wc -c /var/log/uart_echo").strip())

# Step 3: chmod + start
r("chmod 755 /var/log/uart_echo")
r("/var/log/uart_echo /dev/ttyS1 921600 > /dev/null 2>&1 &")
time.sleep(0.5)
pid = r("ps | grep '/var/log/uart_echo' | grep -v grep").strip()
print("uart_echo PID: " + pid)
print()
print("=== ttyS1 @921600 回环已就绪 ===")
print("PC串口助手连 PE21(RX)/PE22(TX) @921600 8N1")
print("发送任意数据, V3s 收到后立即回复相同数据")
print("测试完告诉我")
c.close()
