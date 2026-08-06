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

## 三、开发进度（已完成 ✓）

1. ✅ **地址常量 + 完整帧类型修正**（`162a757`）：DEVICE_PING=0x28, DEVICE_INFO=0x29, PARAMETER_SETTINGS_ENTRY=0x2B, READ=0x2C, WRITE=0x2D, COMMAND=0x32；地址补 RC_RX=0xEC, RADIO_TX=0xEE, CRSF_RX=0xEA
2. ✅ **Heartbeat + 扩展头帧 + Device_Ping**（`162a757`）：crsf_pack_heartbeat / crsf_pack_ext_frame / crsf_pack_device_ping
3. ✅ **参数协议**（`0285b0b`）：crsf_param_type_t + crsf_pack_device_info + crsf_param_parse_entry
4. ✅ **Parameter Read/Write**（`d430690`）：crsf_pack_param_read/write + crsf_param_parse_dev_info
5. ✅ **回传状态机 + 参数表**（`91e394f`）：crsf_handle_request + g_crsf_params + crsf_rx_thread 接入
6. ✅ **主机侧验证**：CRC-8 表 / 帧打包 / Device_Ping→Device_Info / Parameter_Read→Settings_Entry 全部 CRC 正确

## 四、剩余待做

1. 真机验证 CRSF 回传（需接收机/飞控发 Device_Ping）
2. ELRS 链路统计增强（0x29 变体字段）
3. Subset_RC / 11_bits 帧类型
4. App/配置对接：web_server 暴露 CRSF 参数配置端点

## 五、CRSF-Lua 桥接 (新分支 feature/crsf-lua-bridge)

已完成:
- M1: V3s --crsf-bridge 模式 (UART0 CRSF 帧 ↔ 网口 UDP 65532 透明转发), 提交 1e75ebd
- M2: App LuaJ 引擎 + EdgeTX API 绑定 (crossfireTelemetryPush/lcd), 提交 a41aaff
- M3: elrsV3.lua + LuaParamActivity 参数界面, 提交 a41aaff
- 固件: rootfs_bridge.squashfs (b041d706) + spi_image_bridge.bin (a9b36be7)
- APK: app-debug.apk (含 Lua 引擎 + 参数界面)

待验证 (M4, 设备离线):
- 部署 bridge 固件 + 启动 --crsf-bridge
- App 连 V3s 网口 → Lua 参数界面 → ELRS 模块参数读写
