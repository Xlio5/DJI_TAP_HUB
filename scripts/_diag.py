import paramiko, time
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=10, allow_agent=False, look_for_keys=False, banner_timeout=8)
def r(cmd):
    _, out, _ = c.exec_command(cmd); time.sleep(0.3)
    return out.read().decode(errors="replace")

print("=== 1. uart_echo process ===")
print(r("ps | grep uart_echo | grep -v grep || echo DEAD"))

print("=== 2. ttyS1 exists? ===")
print(r("ls -la /dev/ttyS1 2>/dev/null; echo exit=$?"))

print("=== 3. dji_rc running? ===")
print(r("ps | grep dji_rc | grep -v grep || echo NOT_RUNNING"))

print("=== 4. cmdline ===")
print(r("cat /proc/cmdline"))

print("=== 5. kernel version ===")
print(r("uname -a"))

print("=== 6. dmesg UART ===")
out = r("dmesg | grep -i uart | head -8")
print(out if out else "(none)")

print("=== 7. try running uart_echo directly ===")
print(r("stty -F /dev/ttyS1 921600 raw -echo 2>&1; /var/log/uart_echo /dev/ttyS1 921600 2>&1 &"))
time.sleep(2)
print(r("ps | grep uart_echo | grep -v grep || echo STILL_DEAD"))
print(r("dmesg | tail -3"))

c.close()
