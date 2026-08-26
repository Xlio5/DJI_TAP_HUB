"""SSH 手动跑 getty 对比参数顺序 + 检查 ttyS0 输出路径"""
import paramiko, time

def ssh_run(cmd, timeout=10):
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

def show(title, cmd, timeout=10):
    out, err, rc = ssh_run(cmd, timeout)
    print(f"\n===== {title} =====")
    print(out.strip() if out.strip() else "(无 stdout)")
    if err.strip(): print(f"[stderr] {err.strip()}")
    print(f"[exit {rc}]")

# 1. inittab 参数顺序: getty -L ttyS0 115200 (TTY 在前)
show("1. getty -L ttyS0 115200 (inittab 顺序, 读 /dev/null)",
     "timeout 3 /sbin/getty -L ttyS0 115200 vt100 </dev/null 2>&1; echo exit=$?")

# 2. S99 参数顺序: getty -L 115200 ttyS0 (BAUD 在前)
show("2. getty -L 115200 ttyS0 (BAUD 在前, 读 /dev/null)",
     "timeout 3 /sbin/getty -L 115200 ttyS0 vt100 </dev/null 2>&1; echo exit=$?")

# 3. 检查 /etc/issue
show("3. /etc/issue 内容", "ls -la /etc/issue 2>&1; cat /etc/issue 2>&1 | od -c | head -5")

# 4. busybox getty 版本/用法
show("4. busybox getty usage", "busybox 2>&1 | head -1; /sbin/getty 2>&1 | head -10")

# 5. 当前 getty 进程的 wchan(内核等待点)
show("5. getty wchan/state", "G=$(pidof getty); cat /proc/$G/wchan 2>/dev/null; echo; grep State /proc/$G/status")

# 6. ttyS0 当前 termios (用 cat 看 /proc, 不用 stty 避免 ENOTTY 误判)
show("6. ttyS0 驱动状态", "cat /proc/tty/driver/serial")
