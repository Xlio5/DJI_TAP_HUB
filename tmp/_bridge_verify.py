"""M4 验证: V3s bridge 双向转发 (UART0 ↔ 网口 UDP 65532)
电脑 COM10 连 V3s UART0 (115200 8N1)
电脑 IP 192.168.144.88, V3s IP 192.168.144.66
"""
import serial, socket, time, threading, struct

V3S = "192.168.144.66"
PORT = 65532
CRSFBR_MAGIC = 0x46534352  # "CRSF" little-endian

# 测试 CRSF 帧 (Device_Ping): [0xC8][len=4][0x28][dest=0xEE][orig=0xEA][crc]
PING_FRAME = bytes([0xC8, 0x04, 0x28, 0xEE, 0xEA, 0x0D])

def crc8(data):
    t = []
    for i in range(256):
        c = i
        for _ in range(8):
            c = ((c << 1) ^ 0xD5) & 0xFF if (c & 0x80) else (c << 1) & 0xFF
        t.append(c)
    crc = 0
    for b in data:
        crc = t[(crc ^ b) & 0xFF]
    return crc

def make_frame(ftype, payload):
    # 扩展帧: [0xC8][len][type][dest][orig][payload][crc]
    data = bytes([0xC8, len(payload)+4, ftype, 0xEE, 0xEA]) + payload
    return data + bytes([crc8(data)])

print("=== 电脑 COM10 串口 ===")
try:
    ser = serial.Serial("COM10", 115200, timeout=1)
    print(f"COM10 已打开 @115200 8N1: {ser.name}")
except Exception as e:
    print(f"COM10 打开失败: {e}")
    raise SystemExit(1)

print("\n=== 测试 1: 网口 → UART0 (电脑发 UDP, 电脑 COM10 收) ===")
udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
frame = make_frame(0x2C, bytes([0x01, 0x00]))  # Parameter_Read id=1
pkt = struct.pack("<I", CRSFBR_MAGIC) + frame
udp.sendto(pkt, (V3S, PORT))
print(f"已发送 UDP {V3S}:{PORT} 帧: {frame.hex()}")
# 读 COM10 等 V3s 转发
time.sleep(0.5)
got = ser.read(64)
if got:
    print(f"COM10 收到 {len(got)}B: {got.hex()}")
    print("✓ 网口→UART0 转发成功" if got else "✗")
else:
    print("COM10 未收到 (超时)")

print("\n=== 测试 2: UART0 → 网口 (电脑 COM10 发, 电脑 UDP 监听收) ===")
# 启动 UDP 监听
recv_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
recv_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
recv_sock.bind(("0.0.0.0", PORT))
recv_sock.settimeout(3)
# 电脑 COM10 发 Device_Ping
ser.write(PING_FRAME)
print(f"COM10 已发送: {PING_FRAME.hex()}")
try:
    data, addr = recv_sock.recvfrom(128)
    print(f"UDP 收到 {len(data)}B from {addr}: {data.hex()}")
    # 检查 magic
    magic = struct.unpack("<I", data[:4])[0]
    if magic == CRSFBR_MAGIC:
        print(f"✓ UART0→网口 转发成功 (magic CRSF, 帧: {data[4:].hex()})")
    else:
        print(f"✗ magic 不对: 0x{magic:08X}")
except socket.timeout:
    print("UDP 未收到 (超时)")

ser.close()
udp.close()
recv_sock.close()
print("\n[done]")
