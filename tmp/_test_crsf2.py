"""主机侧验证修复后 CRSF 逻辑 (含 dest 参数 + vlen 修正)"""
T = []
for i in range(256):
    c = i
    for _ in range(8):
        c = ((c << 1) ^ 0xD5) & 0xFF if (c & 0x80) else (c << 1) & 0xFF
    T.append(c)
def crc8(d):
    c = 0
    for b in d: c = T[(c ^ b) & 0xFF]
    return c
def pack_ext(addr, t, dest, orig, pl):
    d = bytes([addr, len(pl)+4, t, dest, orig]) + pl
    return d + bytes([crc8(d)])

# 1. Device_Ping → Device_Info (dest = 请求 orig)
ping = pack_ext(0xEA, 0x28, 0xEE, 0xEC, b"")   # orig=0xEC
req_orig = ping[4]
assert req_orig == 0xEC, "orig 提取错误"
# 响应 Device_Info: dest = req_orig
pl = bytes([0x01,0x46,0x01,0x01,0x04,0x02]) + b"V3s-Hub" + b"\x00"*9
info = pack_ext(0xEE, 0x29, req_orig, 0xEE, pl)
print(f"Device_Ping(orig=0x{req_orig:02X}) → Device_Info dest=0x{info[3]:02X} (应 0x{req_orig:02X})")
assert info[3] == req_orig, "响应 dest 错误"
assert crc8(info[:-1]) == info[-1], "CRC 错误"
print("✓ Device_Ping → Device_Info dest=orig 正确, CRC 正确")

# 2. Parameter_Write 值长度 (不含 CRC)
# 帧: [EE][len=7][2D][C8][EE][id=1][chunk=0][value=0x2A][crc]
# plen(值1) + 4 + crc... 实际: addr+len+type+dest+orig+id+chunk+value+crc = 9 字节
pl = bytes([0x01, 0x00, 0x2A])   # id, chunk, value(1B)
wr = pack_ext(0xEA, 0x2D, 0xEE, 0xEA, pl)
print(f"\nParameter_Write 帧: {wr.hex()} (整帧 {len(wr)}B)")
flen = len(wr)
vlen = flen - 8   # 修复后
print(f"vlen = {flen} - 8 = {vlen} (值 1 字节, 不含 CRC)")
assert vlen == 1, f"vlen 应=1, 得 {vlen}"
assert crc8(wr[:-1]) == wr[-1], "CRC 错误"
print("✓ Parameter_Write vlen 正确 (不含 CRC)")

print("\n=== 修复后验证全部通过 ===")
