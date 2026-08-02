"""解析抓到的 ttyS1 原始字节流, 找出 SPECIAL/0x02 帧, dump payload 按键位"""
import re

# 从抓包复制过来的十六进制
hexdata = """
551a04b1060edb0f0001020000042000010840000200000ababf
55551a04b1060ede0f0001020000042000010840000200000af2bc
55551a04b1060ee30f0001020000042000010840000200000a7553
55551a55551a04b1060eee0f0001020000042000010840000200000a72af
555555551a04b1060ef90f0001020000042000010840000200000a6aa3
55551a04b1060efd0f0001020000042000010840000200000ac558
550455551a04b1060e05100001020000042000010840000200000abe02
5555555555
"""

data = bytes.fromhex(re.sub(r'\s+', '', hexdata))

# 找 SOF = 0x55, 尝试解析每个包
i = 0
while i < len(data):
    if data[i] != 0x55:
        i += 1
        continue
    # 解析 DUML 头: ver_len = buf[1] | buf[2]<<8
    if i + 4 > len(data): break
    ver_len = data[i+1] | (data[i+2] << 8)
    pkt_len = ver_len & 0x3FF
    version = (ver_len >> 10) & 0x3F
    if pkt_len < 13 or pkt_len > 1024 or version > 1:
        i += 1
        continue
    if i + pkt_len > len(data): break
    cmd_set = data[i+9]
    cmd_id = data[i+10]
    payload = data[i+11:i+11+pkt_len-13]
    print(f"包@{i}: len={pkt_len} ver={version} cmd_set={cmd_set} cmd_id=0x{cmd_id:02X} payload_len={len(payload)}")
    if cmd_set == 1 and cmd_id == 0x02:
        # SPECIAL/0x02, dump payload
        print(f"  payload: {payload.hex(' ')}")
        # 按键字节 pl[10..12]
        if len(payload) >= 13:
            print(f"  pl[10]={payload[10]:02X} pl[11]={payload[11]:02X} pl[12]={payload[12]:02X}")
            print(f"  pl[12] bits: STOP={(payload[12]>>4)&1} REC={(payload[12]>>5)&1} SHOT={(payload[12]>>0)&1} mode={(payload[12]>>2)&0x3}")
            print(f"  pl[10] bits: FOCUS={(payload[10]>>6)&1}")
            # 扫描所有位, 找出非零的候选 C1/C2/C3
            print(f"  pl[10] 二进制: {payload[10]:08b}")
            print(f"  pl[11] 二进制: {payload[11]:08b}")
            print(f"  pl[12] 二进制: {payload[12]:08b}")
    i += pkt_len
