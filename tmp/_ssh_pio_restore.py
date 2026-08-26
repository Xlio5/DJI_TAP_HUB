"""验证: devmem 把 PB8/PB9 改回 UART0 功能后, UART0 TX 是否恢复"""
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

out, _ = ssh_run("devmem 0x01C2082C 32")
print(f"修改前 PB_CFG2 (0x2C) = {out.strip()}")

# 尝试 UART0 功能值: 先试 2 (sunxi uart 常见功能号), 不行试 3
for val in (0x22, 0x33):
    ssh_run(f"devmem 0x01C2082C 32 0x{val:08x}")
    res = {}
    th = threading.Thread(target=listen, args=(4, f"after_{val}", res)); th.start()
    time.sleep(0.3)
    out, _ = ssh_run("for i in 1 2 3; do echo 'UART0-RECOVER-$i' > /dev/ttyS0; sleep 0.3; done")
    th.join()
    got = res.get(f"after_{val}", b"")
    print(f"PB8/9={val>>4} 后 echo: COM10 收 {len(got)}B -> {got[:80]!r}")
    if got:
        print(f"✅ UART0 TX 恢复! PB8/PB9 功能值 = {val>>4}")
        break
else:
    print("❌ 改回 UART0 功能值后 TX 仍未恢复, 可能不是 pinmux 或需要其他值")
