"""SSH 对比 getty 两种参数顺序的输出行为"""
import paramiko

def ssh_run(cmd, timeout=15):
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect("192.168.144.66", 22, "root", "root", timeout=10,
              allow_agent=False, look_for_keys=False, banner_timeout=10)
    i, o, e = c.exec_command(cmd, timeout=timeout)
    out = o.read().decode("utf-8", "replace")
    err = e.read().decode("utf-8", "replace")
    rc = o.channel.recv_exit_status()
    c.close()
    return out, err, rc

def show(title, cmd, timeout=15):
    out, err, rc = ssh_run(cmd, timeout)
    print(f"\n===== {title} =====")
    print(out.strip() if out.strip() else "(无 stdout)")
    if err.strip(): print(f"[stderr] {err.strip()}")
    print(f"[exit {rc}]")

# A. inittab 顺序: getty -L ttyS0 115200  (TTY 在前)  → 输出重定向文件
show("A. getty -L ttyS0 115200 (TTY在前) → 输出到文件",
     "sh -c '/sbin/getty -L ttyS0 115200 vt100 </dev/null >/tmp/gtA.out 2>&1 & GP=$!; sleep 3; kill $GP 2>/dev/null; echo ---A文件内容---; cat /tmp/gtA.out | od -c | head -10; ls -la /tmp/gtA.out'")

# B. S99/标准顺序: getty -L 115200 ttyS0  (BAUD 在前) → 输出重定向文件
show("B. getty -L 115200 ttyS0 (BAUD在前) → 输出到文件",
     "sh -c '/sbin/getty -L 115200 ttyS0 vt100 </dev/null >/tmp/gtB.out 2>&1 & GP=$!; sleep 3; kill $GP 2>/dev/null; echo ---B文件内容---; cat /tmp/gtB.out | od -c | head -10; ls -la /tmp/gtB.out'")

# C. 对比: 直接往 /dev/ttyS0 写数据 + 同时 COM10 不在线, 只确认 write 层
show("C. 用 dd 从 ttyS0 读超时测试 (确认 ttyS0 读路径)",
     "timeout 1 dd if=/dev/ttyS0 bs=1 count=1 2>&1; echo dd_exit=$?")

# D. 检查 getty 实际打开的 ttyS0 termios (ioctl 方式)
show("D. ttyS0 波特率+flags (stty speed 单独测)",
     "stty -F /dev/ttyS0 speed 2>&1; echo; stty -F /dev/ttyS0 115200 2>&1; echo set_exit=$?; stty -F /dev/ttyS0 speed 2>&1")
