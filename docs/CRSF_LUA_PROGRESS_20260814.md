# CRSF-Lua 真机调试进度（2026-08-14）

> 本次会话完成的工作 + 当前状态 + 遗留问题
> 分支：feature/crsf-lua-bridge

---

## 一、本次会话完成的关键工作

### 1. 根因定位：ELRS 响应回传链路为什么一直不通

对照参考实现 `c:/my_project/elrs_lua_python/`（crsf.py + elrs_serial.py），
通过 COM10 直连实验，定位到 **4 个叠加根因**：

| # | 根因 | 证据 | 状态 |
|---|---|---|---|
| 1 | **ping 帧 addr 字节错误**：`0xC8`（FC 地址），ELRS 只认 `0xEE`（TX 模块） | 直连实验：`ee042800ea54` 响应，`c8042800ea54` 无响应 | ✅ 已修 |
| 2 | **CRC 写死 0x55 错误**：应为 `0x54`（crc8 poly 0xD5 算出） | 参考实现 `build_extended_frame` 自动算 | ✅ 已修 |
| 3 | **电脑桥没 drop DTR/RTS**：CP210x 在 DTR/RTS assert 时把 ELRS MCU 按在复位，不响应 | 实验：DTR=False 才响应，DTR=True 无响应 | ✅ 已修（_com_bridge.py） |
| 4 | **发 5 帧即停，撞上 ELRS 波特率轮换（~7s）**：ELRS 模块的 handset UART 每 ~7s 轮换一次波特率，必须**持续 ping + 等待** | elrs_serial.py find_baud 注释 + 实验 | ✅ 已确认需持续 ping |

### 2. ELRS 响应回传链路验证打通

**电脑桥监测确认完整回传**：
```
[V3s→ELRS] 6B: ee042800ea54                ← V3s 广播 Device_Ping（正确帧）
[ELRS→V3s] 15B: ea0d3aeaee10000186a0fffffc7c61   ← ELRS Status (0x3A)
[ELRS→V3s] 32B: ea1e29eaee542d31342039303020545800454c5253...  ← Device_Info (0x29) "T-14 900 TX"
```
V3s uart_bridge 日志同步出现 `[uart→net] 32B` —— **ELRS 响应已成功回传到 V3s UDP**。

### 3. 网口 magic 统一

| 端 | 旧 | 新 | 说明 |
|---|---|---|---|
| 固件 dji_rc.cpp | `CRSFBR_MAGIC=0x46534352` | 不变 | 字节 `52 53 43 46` |
| App CrsfBridge.kt | `MAGIC=0x46534352` | 不变 | 与固件一致 |
| V3s uart_bridge.c（测试程序） | `"RCSF"` = `52 43 53 46` | **`\x52\x53\x43\x46`** | ✅ 对齐 App/固件 |
| V3s udp_send/udp_ping.c | `"RCSF"` | **`\x52\x53\x43\x46`** | ✅ 对齐 |

**关键点**：之前 App → uart_bridge 链路走不通，一部分原因就是 magic 不一致（App 发 `52 53 43 46`，uart_bridge 认 `52 43 53 46`，被判 no-magic 丢弃）。

### 4. App 侧帧构造修复

- **LuaEngine.kt** `buildCrsfFrame`：
  - `frame[0]`：0xC8 → **0xEE**（addr = CRSF TX 模块）
  - CRC 起点：`crc8(frame, len)` → **`crc8(frame, 2, len)`**（只对 [type][dest][orig][payload] 计算，参考实现）
- **LuaParamController.kt** `buildDevicePing`：
  - `frame[0]`：0xC8 → **0xEE**（addr）
  - `frame[3]`：0xEE → **0x00**（dest = 广播）
  - 帧长：7 → **6**（正确长度）
  - CRC 起点：→ **`crc8(frame, 2, 5)`**
- **build.gradle.kts**：App 版本 1.5.9 → **1.6.0**（versionCode 38→39）

### 5. 当前链路状态（V3s）

- V3s 跑 **/tmp 的 uart_bridge**（PID 已更新，统一 magic 版 d8c73849）
- 电脑桥 = 修复版 `_com_bridge.py`（DTR/RTS drop）

---

## 二、当前进度

### ✅ 已完成
1. ELRS 响应回传链路物理打通（V3s ping → ELRS → 响应回传 → V3s UDP）
2. App 帧构造修复（ping addr/dest/CRC/magic 对齐）
3. App 编译通过（v1.6.0，md5 86AFE6E0）

### ⚠️ 遗留问题
1. **V3s 测试程序传输不稳**：base64 分块上传 udp_send/udp_ping 到 V3s 时 "truncated input"
   - uart_bridge 已成功同步（md5 校验通过）
   - udp_send/udp_ping 需重传（用更小分块 + 长度校验）
2. **V3s 本地 UDP 投递**：udp_send 发 10.0.0.1:65532 出现 `no-magic 10B`
   - 因为 V3s 上的 udp_send 还是旧 magic（`RCSF`）→ 已确认根因，待同步
3. **App 真机部署**：adb 端口不稳定（DJI RC 重启后变），需重连 adb
4. **App 走 tun0 路由**：App CrsfBridge 发包走 wlan0 不到 V3s（历史遗留，未解决）
5. **固件固化**：V3s 跑 /tmp 测试版 uart_bridge，不是固件 dji_rc

---

## 三、待办（按优先级）

1. **同步 V3s udp_send/udp_ping 到统一 magic**（用 `_sync_tools_v2.py` 小分块 + 长度校验）
2. **重连 adb**（`adb connect 10.169.25.210:43719` 或重新查询）
3. **部署 App v1.6.0 到 DJI RC**（adb install -r）
4. **验证 App 加载 ELRS Lua 参数**（真机，非 mock）
5. **解决 App 走 tun0 路由**（如仍不通）
6. **固件固化**：把验证过的 bridge 逻辑固化到 dji_rc/固件
7. 版本号同步 + 清理测试残留

---

## 四、关键文件

| 文件 | 说明 |
|---|---|
| `tmp/_com_bridge.py` | 电脑桥（已修 DTR/RTS drop） |
| `tmp/_uart_bridge.c` | V3s 测试 bridge（统一 magic） |
| `tmp/_udp_ping.c` | V3s 持续 ping 工具（统一 magic） |
| `tmp/_udp_send.c` | V3s 单发 ping（统一 magic） |
| `tmp/_continuous_ping.py` | 直连 COM10 持续 ping 验证（根因实验） |
| `tmp/_rootcause_ping.py` | 根因验证实验（addr/CRC/DTR） |
| `tmp/_com_bridge_test.py` | 一体测试电脑桥 + V3s ping |
| `tmp/_sync_bridge_version.py` | 同步 uart_bridge 到 V3s |
| `tmp/_sync_tools_v2.py` | 同步 udp_send/udp_ping（小分块） |
| `android/.../crsf/LuaEngine.kt` | App Lua 引擎（帧构造已修） |
| `android/.../crsf/LuaParamController.kt` | App 参数控制器（ping 已修） |
| `android/.../crsf/CrsfBridge.kt` | App UDP 桥（magic 与固件一致） |
