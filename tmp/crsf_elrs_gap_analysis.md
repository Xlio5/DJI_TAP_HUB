# CRSF/ELRS 适配差距分析

> 基于 ax12 app 逆向报告（CrsfSerial + ELRS遥控器V1.1.2）对照现有 crsf.h/c
> 日期: 2026-08-06

## 一、现有 crsf.h/c 已实现（与逆向一致 ✓）

- CRC-8 poly 0xD5 查表（表[0]=0x00, 表[1]=0xD5, 特征值 213=0xD5）✓
- 帧格式 `[addr][len][type][payload][crc]`，len ≤ 0x3E，整帧 ≤ 62B ✓
- RC_CHANNELS_PACKED(0x16)：16 通道 × 11bit 打包/解包 ✓
- 回传解析：LINK_STATISTICS(0x14/0x29)、GPS(0x02)、BATTERY(0x08)、ATTITUDE(0x1E)、VARIO(0x07)、FLIGHT_MODE(0x21) ✓
- 地址：0xC8=TX、0xEE=RX、0xEA=BROADCAST ✓

## 二、逆向报告里有、现有代码缺的

### 1. 参数协议（ELRS Lua 配置）—— 核心缺失
逆向 `I.c` 参数类型枚举（UINT_8..COMMAND, bit7=hidden）：
- Parameter_Ping_Devices(0x28/40)
- Device_Information(0x29/41)
- Settings_Entry(0x2B/43)
- Settings_Read(0x2C/44)
- Value_Write(0x2D/45)
现有 crsf.h 有 DEVICE_PING(0x1C) 但无完整参数协议。

### 2. Heartbeat 帧（D.i 构造）
`[0xC8][len=4][Heartbeat(0x0B)][device_hi][device_lo][CRC]`
现有无。

### 3. 设备地址语义
逆向 ELRS遥控器：`Flight_controller=200(0xC8)`、`RC_Transmitter=238(0xEE)`
现有 crsf.h: `CRSF_ADDR_TX=0xC8`（发射机→接收机）、`CRSF_ADDR_RX=0xEE`
**注意**：0xC8 在逆向里是 Flight_controller（200），0xEE 是 RC_Transmitter（238）。现有代码语义可能需澄清——0xC8 作为下行（TX→RX）地址是 CRSF 标准，但 0xEE 作为 RX 上行地址需确认。参考 CRSF 官方：
- 0xC8 = CRSF_ADDRESS_FLIGHT_CONTROLLER
- 0xEE = CRSF_ADDRESS_RADIO_TRANSMITTER
- 0xEA = CRSF_ADDRESS_CRSF_RECEIVER (实际接收机)
现有 `CRSF_ADDR_RX=0xEE` 应改为 0xEA（接收机），0xEE 是发射机地址。

### 4. 链路统计细节
逆向 `packetLinkStatistics`：ELRS 变体 0x29 有更丰富的字段（天线数、RF 模式等）。现有解析 8 字节（up/dn rssi/snr/quality），可补 ELRS 特有字段。

### 5. 完整帧类型面（逆向 I.e 枚举）
现有已覆盖主要的。可补：
- Subset_RC_Channels(0x17/23)
- 11_bits(0x18/24)
- Heartbeat(0x0B/11)
- OpenTX_Sync(0x10/16) — 已有 CRSF_FRAMETYPE_OPEN_TX_SYNC

## 三、开发计划（按功能点 commit）

1. **地址常量修正**：CRSF_ADDR_RX 0xEE → 0xEA；明确 TX/RX 语义
2. **Heartbeat 帧**：crsf_pack_heartbeat()
3. **参数协议**：Parameter_Ping/Device_Info/Settings_Entry/Read/Value_Write 打包+解析
4. **ELRS 链路统计增强**：0x29 变体字段
5. **完整帧类型**：Subset_RC、11_bits 等
6. **App/配置对接**：web_server 暴露 CRSF 参数配置端点
