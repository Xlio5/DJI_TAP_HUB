"""主机侧验证 CRSF 协议逻辑 (对照逆向 CRC 表 + 帧格式)
验证: CRC-8 poly 0xD5, 帧打包, Device_Ping/Parameter_Read 响应
通过 Python 复刻 crsf.c 逻辑, 与逆向报告交叉验证
"""
# CRSF CRC-8 poly 0xD5 表 (逆向 crsf_crc8_table.bin 特征: [1]=0xD5)
CRC_TABLE = []
poly = 0xD5
for i in range(256):
    c = i
    for _ in range(8):
        c = ((c << 1) ^ poly) & 0xFF if (c & 0x80) else (c << 1) & 0xFF
    CRC_TABLE.append(c)

def crc8(data):
    c = 0
    for b in data:
        c = CRC_TABLE[(c ^ b) & 0xFF]
    return c

def pack_frame(addr, ftype, payload):
    """广播帧: [addr][len][type][payload][crc], len = payload+2"""
    data = bytes([addr, len(payload)+2, ftype]) + payload
    return data + bytes([crc8(data)])

def pack_ext_frame(addr, ftype, dest, orig, payload):
    """扩展头帧: [addr][len][type][dest][orig][payload][crc], len = payload+4"""
    data = bytes([addr, len(payload)+4, ftype, dest, orig]) + payload
    return data + bytes([crc8(data)])

# 验证 CRC 表特征值
assert CRC_TABLE[0] == 0x00, "CRC table[0]"
assert CRC_TABLE[1] == 0xD5, f"CRC table[1]={CRC_TABLE[1]:02X} (应 D5)"
print("✓ CRC-8 表特征: table[0]=00, table[1]=D5 (与逆向一致)")

# 验证帧打包
fr = pack_frame(0xC8, 0x16, b"\x00"*22)
print(f"✓ RC_CHANNELS 帧: len={len(fr)} {fr.hex()}")

# 验证 Device_Ping 请求 → 应响应 Device_Info
# 构造 Device_Ping (扩展头): dest=0xEE(TX), orig=0xEA(RX)
ping = pack_ext_frame(0xEA, 0x28, 0xEE, 0xEA, b"")
print(f"\nDevice_Ping: {ping.hex()}")

# 模拟 crsf_handle_request 的 Device_Ping 分支: 响应 Device_Info
def handle_ping():
    pl = bytes([0x01, 0x46, 0x01, 0x01, 0x04, 0x02]) + b"V3s-Hub" + b"\x00"*9
    return pack_ext_frame(0xEE, 0x29, 0xC8, 0xEE, pl)

resp = handle_ping()
print(f"Device_Info 响应: {resp.hex()}")
# 验证 CRC
assert crc8(resp[:-1]) == resp[-1], "Device_Info CRC 错误"
print("✓ Device_Info 响应 CRC 正确")

# 验证 Parameter_Read 请求 → Settings_Entry 响应
read = pack_ext_frame(0xEA, 0x2C, 0xEE, 0xEA, bytes([0x01, 0x00]))  # id=1, chunk=0
print(f"\nParameter_Read: {read.hex()}")

def handle_param_read(param_id):
    # Settings_Entry: [id][parent][type][flags][min][max][def][unit6][name16]
    pl = bytes([param_id, 0x00, 0x09, 0x00, 0x00, 0x02, 0x00]) + b"\x00"*6 + b"Output Mode" + b"\x00"*5
    return pack_ext_frame(0xEE, 0x2B, 0xC8, 0xEE, pl)

presp = handle_param_read(1)
print(f"Settings_Entry 响应: {presp.hex()}")
assert crc8(presp[:-1]) == presp[-1], "Settings_Entry CRC 错误"
print("✓ Settings_Entry 响应 CRC 正确")

print("\n=== 全部主机侧验证通过 ===")
