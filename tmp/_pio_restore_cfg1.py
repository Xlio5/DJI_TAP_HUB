"""决定性验证: devmem 把 PB_CFG1@0x28 的 PB8/PB9 改回 UART0(3) 后, UART0 TX 恢复"""
import serial, paramiko, threading, time

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

def listen(seconds, key, result):
    s = serial.Serial("COM10", 115200, timeout=0.2)
    buf = b""
    end = time.time() + seconds
    while time.time() < end:
        d = s.read(1024)
        if d: buf += d
    s.close()
    result[key] = buf
    print(f"[{key}] COM10 收 {len(buf)}B")

# 1. kill dji_rc 防再次写 PIO
out, _ = ssh_run("killall dji_rc 2>/dev/null; sleep 1; echo killed")
print("kill dji_rc:", out.strip())

# 2. 改 PB_CFG1@0x28: PB8/PB9 = 3 (UART0), 保留其他位
out, _ = ssh_run("devmem 0x01C20828 32")
print(f"修改前 0x28 = {out.strip()}")
out, _ = ssh_run("devmem 0x01C20828 32 0x00777733")
out, _ = ssh_run("devmem 0x01C20828 32")
print(f"修改后 0x28 = {out.strip()} (PB8/PB9 应为 3)")
out, _ = ssh_run("devmem 0x01C20828 32 | awk '{print substr($0,length($0)-1,1)}'")

# 3. COM10 监听 + echo 写 ttyS0
res = {}
th = threading.Thread(target=listen, args=(5, "after_restore", res)); th.start()
time.sleep(0.3)
out, _ = ssh_run("for i in 1 2 3 4 5; do echo 'UART0-RESTORED-$i' > /dev/ttyS0; sleep 0.3; done")
th.join()
got = res.get("after_restore", b"")
print(f"\n=== COM10 收到 {len(got)}B ===")
print(got.decode('utf-8','replace')[:200] if got else "(仍静默)")
print("✅ UART0 TX 恢复! 确认根因: aux_tmux_set 破坏 PB8/PB9 pinmux" if got else "❌ 仍无输出, 需进一步排查")
