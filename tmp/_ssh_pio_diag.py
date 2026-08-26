"""SSH 读 PIO 寄存器, 确认 PB8/PB9 (UART0) pinmux 是否被破坏 + 排查 aux_tmux_set 偏移"""
import paramiko

def ssh_run(cmd, timeout=10):
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect("192.168.144.66", 22, "root", "root", timeout=10,
              allow_agent=False, look_for_keys=False, banner_timeout=10)
    i, o, e = c.exec_command(cmd, timeout=timeout)
    out = o.read().decode("utf-8", "replace")
    err = e.read().decode("utf-8", "replace")
    c.close()
    return out, err

def show(title, cmd):
    out, err = ssh_run(cmd)
    print(f"\n===== {title} =====")
    print(out.strip() if out.strip() else "(无输出)")
    if err.strip(): print(f"[stderr] {err.strip()}")

# devmem 可用性 + 读 PIO 关键寄存器
show("0. devmem 可用性", "which devmem 2>&1")

# PIO @0x01C20800, 读 PB 相关寄存器 (探测 0x24-0x48 区间)
show("1. PIO 寄存器 0x01C20800+0x20..0x4C (每次一行 hex)",
     "for o in 0x20 0x24 0x28 0x2c 0x30 0x34 0x38 0x3c 0x40 0x44 0x48 0x4c; do a=$((0x01C20800 + $o)); v=$(devmem $a 32 2>/dev/null); echo \"+$o -> $a = $v\"; done")

# 读 PB_CFG2 定位 PB8/PB9 (UART0), 分析 CFG 位
show("2. PB_CFG2 (PB8-11) 详细位分析",
     "v=$(devmem $((0x01C20800 + 0x2C)) 32 2>/dev/null); echo \"PB_CFG2=$v\"; echo \"PB8(bit0-3)=$(( ($v >> 0) & 0xF ))\"; echo \"PB9(bit4-7)=$(( ($v >> 4) & 0xF ))\"; echo \"PB10(bit8-11)=$(( ($v >> 8) & 0xF ))\"; echo \"PB11(bit12-15)=$(( ($v >> 12) & 0xF ))\"")

# 尝试读 /proc/tty/driver/serial 的替代 - sysfs ttyS0
show("3. sysfs ttyS0 设备确认", "ls -la /sys/class/tty/ttyS0/ 2>&1 | head -3; cat /sys/class/tty/ttyS0/type 2>&1")

# dji_rc 是否还在跑 + 它的 /dev/mem 使用
show("4. dji_rc 进程 + /dev/mem fd", "pidof dji_rc; ls -la /proc/$(pidof dji_rc)/fd 2>/dev/null | grep -E 'mem|tty|sc'")

# 手动重配 PB8/PB9 为 UART0 试试 TX 恢复? (devmem 写 CFG) - 先只读不改
show("5. 内核 pinctrl 当前 pinmux (debugfs)", "ls /sys/kernel/debug/pinctrl/ 2>&1; cat /sys/kernel/debug/pinctrl/*/pinmux-pins 2>&1 | head -5")
