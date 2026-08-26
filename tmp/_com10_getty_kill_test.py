"""决定实验: getty 在跑 vs 被杀 时, 往 ttyS0 写数据, COM10 能否收到
若 getty 在跑时收不到、被杀后能收到 → getty 的 termios 破坏了 UART0 TX"""
import serial, paramiko, threading, time

PORT = "COM10"

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

def listen(seconds, key, result):
    s = serial.Serial(PORT, 115200, timeout=0.2)
    buf = b""
    end = time.time() + seconds
    while time.time() < end:
        d = s.read(1024)
        if d: buf += d
    s.close()
    result[key] = buf
    print(f"[{key}] COM10 收 {len(buf)}B")

# ── 阶段1: getty 在跑, echo 写 ttyS0 ──
print("=== 阶段1: getty 在跑, echo 写 ttyS0 ===")
res = {}
th = threading.Thread(target=listen, args=(6, "with_getty", res)); th.start()
time.sleep(0.3)
out, err, rc = ssh_run("for i in 1 2 3 4 5; do echo 'WITH-GETTY-$i-HELLO' > /dev/ttyS0; sleep 0.3; done; echo done")
print("SSH 返回:", out.strip())
th.join()
print("阶段1 COM10 收到:", res.get("with_getty", b""))
print("阶段1 判定:", "✅ getty 在时 UART0 TX 正常" if res.get("with_getty") else "❌ getty 在时 UART0 TX 无输出")

# ── 阶段2: 杀 getty, 立即 echo 写 ttyS0 ──
print("\n=== 阶段2: 杀 getty 后 echo 写 ttyS0 ===")
res2 = {}
out, err, rc = ssh_run("G=$(pidof getty); kill $G 2>/dev/null; echo killed=$G")
print("杀 getty:", out.strip())
th = threading.Thread(target=listen, args=(6, "no_getty", res2)); th.start()
time.sleep(0.3)
out, err, rc = ssh_run("for i in 1 2 3 4 5; do echo 'NO-GETTY-$i-HELLO' > /dev/ttyS0; sleep 0.3; done; echo done")
print("SSH 返回:", out.strip())
th.join()
print("阶段2 COM10 收到:", res2.get("no_getty", b""))
print("阶段2 判定:", "✅ 杀 getty 后 UART0 TX 恢复" if res2.get("no_getty") else "❌ 杀 getty 后仍无输出")

# 结论
w = res.get("with_getty", b""); n = res2.get("no_getty", b"")
if not w and n:
    print("\n★ 结论: getty 的 termios 破坏了 UART0 TX (getty 在时写不出, 杀了能出)")
elif not w and not n:
    print("\n★ 结论: UART0 TX 设备层坏了 (无论 getty 与否都写不出) — 不是 getty 导致")
elif w and n:
    print("\n★ 结论: UART0 TX 正常 (getty 在也能写) — getty 不打印 login 是 getty 自身问题")
else:
    print("\n★ 结论: 结果异常, 需要更多诊断")
