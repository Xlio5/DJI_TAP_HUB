"""COM10 深度探测: 判断 TX/RX 方向、波特率、getty 是否响应"""
import serial, time

def probe(port, baud, label):
    print(f"\n=== {label}: {port} @{baud} ===")
    try:
        s = serial.Serial(port, baud, timeout=0.4, write_timeout=1)
    except Exception as e:
        print(f"  打开失败: {e}")
        return
    time.sleep(0.2)
    s.reset_input_buffer()

    # 1) 静置读
    time.sleep(0.6)
    d = s.read(1024)
    print(f"  静置读 {len(d)}B: {d[:80]!r}")

    # 2) 发 admin + 回车 (触发 login->password 流程, 会回显)
    s.write(b"admin\r\n")
    end = time.time() + 2.5
    out = b""
    while time.time() < end:
        d = s.read(1024)
        if d: out += d
    print(f"  发 admin 读 {len(out)}B: {out[:200]!r}")

    # 3) 发一串可见字符 + 回车 (判断回显)
    s.write(b"XYZ123\r\n")
    end = time.time() + 2.0
    out = b""
    while time.time() < end:
        d = s.read(1024)
        if d: out += d
    print(f"  发 XYZ123 读 {len(out)}B: {out[:200]!r}")

    s.close()

for baud in (115200, 57600, 9600, 230400):
    probe("COM10", baud, f"COM10 波特率")
