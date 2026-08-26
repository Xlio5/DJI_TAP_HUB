"""SSH 到 V3s 检查 UART0 (ttyS0) 软件层状态 + 主动写测试验证 TX"""
import paramiko, sys, time

HOST = "192.168.144.66"
def ssh_run(cmd, timeout=10):
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, 22, "root", "root", timeout=10, allow_agent=False, look_for_keys=False, banner_timeout=10)
    i, o, e = c.exec_command(cmd, timeout=timeout)
    out = o.read().decode("utf-8", "replace")
    err = e.read().decode("utf-8", "replace")
    rc = o.channel.recv_exit_status()
    c.close()
    return out, err, rc

print("=== 1. /proc/tty/driver/serial (UART0 tx/rx 计数) ===")
out, _, _ = ssh_run("cat /proc/tty/driver/serial")
print(out)

print("=== 2. dmesg console ttyS0 注册 ===")
out, _, _ = ssh_run("dmesg | grep -i 'ttyS0\\|console\\[' | head -8")
print(out)

print("=== 3. getty 进程 + 打开的 fd ===")
out, _, _ = ssh_run("ps w | grep '[g]etty'; G=$(pidof getty); echo '--- getty fd ---'; ls -la /proc/$G/fd/ 2>/dev/null | grep -i tty")
print(out)

print("=== 4. 主动往 /dev/ttyS0 写测试数据 (观察 tx 计数变化) ===")
out, _, _ = ssh_run("cat /proc/tty/driver/serial | grep ttyS0")
print("写入前:", out.strip())
out, _, _ = ssh_run("echo 'UART0-COM10-TEST-OK' > /dev/ttyS0 2>&1; echo 写返回=$?")
print(out.strip())
time.sleep(0.5)
out, _, _ = ssh_run("cat /proc/tty/driver/serial | grep ttyS0")
print("写入后:", out.strip())

print("=== 5. stty ttyS0 状态 ===")
out, _, _ = ssh_run("stty -F /dev/ttyS0 -a 2>&1 | head -2")
print(out)
