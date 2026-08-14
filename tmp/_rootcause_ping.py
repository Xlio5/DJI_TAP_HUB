# -*- coding: utf-8 -*-
"""根因验证: COM10 直连, 对照参考实现的两个关键点
   假设A: ELRS 只响应 addr=0xEE 的 ping (参考实现 _PING), 不响应 addr=0xC8
   假设B: DTR/RTS 必须 drop (False), 否则 CP210x 把 ELRS MCU 按在复位, 不响应
"""
import sys, time
sys.path.insert(0, r"c:\my_project\elrs_lua_python")
import serial
import crsf

PORT = "COM10"
BAUD = 115200

def probe(ser, parser, ping, tag, wait=3.0):
    """发 ping, 读 wait 秒, 返回收到的帧列表"""
    ser.reset_input_buffer()
    got = []
    print(f"\n=== [{tag}] 发 ping: {ping.hex()} ===")
    ser.write(ping); ser.flush()
    deadline = time.time() + wait
    while time.time() < deadline:
        n = ser.in_waiting
        data = ser.read(n) if n else ser.read(1)
        if data:
            for f in parser.feed(data):
                got.append(repr(f))
                print(f"  <- {f!r}")
        time.sleep(0.02)
    if not got:
        print("  无响应")
    return got

def main():
    # 参考实现的 ping: addr=0xEE
    ping_ee = crsf.build_extended_frame(crsf.FRAMETYPE_DEVICE_PING,
                                        crsf.ADDR_BROADCAST,
                                        crsf.ADDR_RADIO_TRANSMITTER,
                                        [], addr=crsf.ADDR_CRSF_TRANSMITTER)
    # V3s 用的 ping: addr=0xC8
    ping_c8 = crsf.build_extended_frame(crsf.FRAMETYPE_DEVICE_PING,
                                        crsf.ADDR_BROADCAST,
                                        crsf.ADDR_RADIO_TRANSMITTER,
                                        [], addr=crsf.ADDR_FLIGHT_CONTROLLER)
    print(f"ping_ee = {ping_ee.hex()}   <- 参考实现 _PING")
    print(f"ping_c8 = {ping_c8.hex()}   <- V3s udp_send 目前用")

    # 第1轮: dtr=False (参考实现行为)
    ser = serial.Serial(PORT, BAUD, timeout=0.2)
    ser.dtr = False
    ser.rts = False
    time.sleep(0.5)   # 模块上电/解除复位
    parser = crsf.FrameParser()
    print("\n########## 第1轮: DTR=RTS=False (参考实现行为) ##########")
    r_ee = probe(ser, parser, ping_ee, "addr=0xEE")
    r_c8 = probe(ser, parser, ping_c8, "addr=0xC8")
    ser.close()
    time.sleep(0.5)

    # 第2轮: dtr=True (电脑桥 _com_bridge 当前行为)
    ser2 = serial.Serial(PORT, BAUD, timeout=0.2)
    # ser2.dtr 保持 pyserial 默认 (True)
    time.sleep(0.5)
    parser2 = crsf.FrameParser()
    print("\n########## 第2轮: DTR/RTS 保持 True (电脑桥当前行为) ##########")
    r2_ee = probe(ser2, parser2, ping_ee, "addr=0xEE")
    ser2.close()

    print("\n===== 结论 =====")
    print(f"第1轮 addr=0xEE: {len(r_ee)} 帧响应;  addr=0xC8: {len(r_c8)} 帧响应")
    print(f"第2轮 addr=0xEE (DTR=True): {len(r2_ee)} 帧响应")
    print("\n完成")

if __name__ == "__main__":
    main()
