"""SSH 诊断 V3s getty/inittab 状态 - 为什么 login 提示不出现"""
import paramiko

def ssh_run(cmd, timeout=8):
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

def show(title, cmd):
    out, err, rc = ssh_run(cmd)
    print(f"\n===== {title} =====")
    print(out.strip() if out.strip() else "(空)")
    if err.strip(): print(f"[stderr] {err.strip()}")
    print(f"[exit {rc}]")

show("1. getty/dji_rc 进程", "ps w | grep -E '[g]etty|[d]ji_rc'")

show("2. getty PID + fd", "G=$(pidof getty); echo PID=$G; ls -la /proc/$G/fd/ 2>/dev/null | grep tty; echo '--- status ---'; grep -E 'State|Name' /proc/$G/status 2>/dev/null")

show("3. /dev/ttyS0 节点", "ls -l /dev/ttyS0; od -A d -t d1 -N 8 /dev/ttyS0 2>&1 | head -1")

show("4. /proc/tty/driver/serial (UART 状态)", "cat /proc/tty/driver/serial")

show("5. inittab ttyS0 行", "grep -vE '^#|^$' /etc/inittab | grep -i tty")

show("6. getty 手动测试 (前台 3 秒, 看输出/错误)", "timeout 3 /sbin/getty -L ttyS0 115200 vt100 </dev/ttyS0 >/dev/ttyS0 2>&1; echo getty_exit=$?")

show("7. dmesg 尾部 (找 tty/serial/getty 错误)", "dmesg | tail -25")

show("8. busybox getty 用法 (确认参数顺序)", "busybox getty 2>&1 | head -8")
