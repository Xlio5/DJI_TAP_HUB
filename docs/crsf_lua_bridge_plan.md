# CRSF-Lua 桥接 + App Lua 引擎 — 实现计划

> 日期: 2026-08-07
> 分支: feature/crsf-lua-bridge
> 目标: 通过 CRSF 双向协议配置射频参数, App 跑 ELRS Lua 脚本生成界面

## 一、架构总览

```
┌─ 遥控器内部 ─────────────────────────────────┐
│  ELRS模块 ──UART0(CRSF双向)──▶ V3s ──网口UDP──▶ App (Lua引擎)
│     │                        │  桥接模式        │
│     └────────────────────────┘  参数帧透明转发    └─ 跑 elrsV3.lua 生成界面
└──────────────────────────────────────────────────┘
```

**核心思路**: V3s 变成 CRSF 桥——UART0 收到的 CRSF 帧转发网口 UDP，App 的 Lua 脚本通过 `crossfireTelemetryPush` 发命令，V3s 转成 CRSF 帧发 UART0。V3s 不做参数决策。

## 二、V3s 侧: crsf-bridge 模式

### 2.1 新启动参数 `--crsf-bridge`
```
dji_rc --crsf-bridge --out-dev /dev/ttyS0 --rcmsg-host <App-IP> --rcmsg-port 65530
```

### 2.2 数据流 (现有 crsf_rx_thread 扩展)
- **下行** (App→UART0): 网口 UDP 收到 CRSF 帧 → 原样写 UART0
- **上行** (UART0→App): 收到的 CRSF 帧按类型分流:
  - 遥测帧 (GPS/BATT/ATT/链路统计) → 现有解析 + UDP TLM (65531)
  - **参数请求帧 (0x28+) → 原样转发网口 UDP (65530)** ← 新增
- 透明转发: 不做 Device_Info/Settings_Entry 内部响应 (禁用 crsf_handle_request)

### 2.3 网口 UDP 协议 (复用 rcmsg/tlm 风格)
```
[magic 4B][type 1B][len 2B][payload]
magic: "CRSF" = 0x465343... 
type:  0x01 = CRSF 帧上行, 0x02 = CRSF 帧下行
```
与现有 rcmsg("RCM1")/tlm("TLM1") 区分。

### 2.4 复用现有
- crsf.h/c 的编解码 (已实现)
- rcmsg_open/send_rcmsg 非阻塞 UDP (已修复)

## 三、App 侧: Lua 引擎

### 3.1 引擎选型 (Android)
| 方案 | 说明 |
|---|---|
| **LuaJ** (默认) | 纯 Java/Android 移植的 Lua 5.2, 无 JNI, 简单可靠 |
| Lua (NDK C) | 性能好, 但 JNI 复杂 |
| LuaC / lua-android | 其他移植 |

**推荐 LuaJ**: 纯 Java 实现, APK 无 JNI 负担, 对 elrsV3.lua 性能足够 (参数界面 UI 不密集)。

### 3.2 绑定的 Lua API (elrsV3.lua 依赖面)
核心 API (从脚本分析):
```lua
-- CRSF 发送
crossfireTelemetryPush(type, {bytes})  -- 核心, 发 CRSF 帧到网口

-- LCD 绘图 (映射到 Android UI)
lcd.drawText(x, y, str, attr)
lcd.getLastPos()
lcd.sizeText()

-- 常量
BOLD, CHAR_UP, CHAR_DOWN, ...

-- 标准库
bit32, string, math, collectgarbage, table
```

### 3.3 Lua 脚本执行模型
```
App 收到网口 CRSF 帧 (Settings_Entry/Device_Info)
  → 转成 Lua 数据回调 (字段值/定义)
  → Lua 脚本 run() 处理 → lcd.drawText 调用
  → App 捕获 drawText → 渲染 Android UI
用户操作 → event() 回调 → Lua → crossfireTelemetryPush → 网口 → V3s → UART0
```

### 3.4 EdgeTX 兼容层
- 实现 EdgeTX 脚本入口约定: `loadScript`/`run`/`event` 全局
- 提供 `model.getInfo()` 等空实现 (兼容其他脚本)
- 这样**其他按 EdgeTX 规范写的 Lua 脚本也能跑** (回答老大的问题)

## 四、里程碑

| 阶段 | 内容 | 验证 | 状态 |
|---|---|---|---|
| **M1** | V3s crsf-bridge 模式 (UART0↔网口转发) | 网口 echo CRSF 帧 | ✅ complete |
| **M2** | App 集成 LuaJ + crossfireTelemetryPush 绑定 | App 能跑简单 Lua | ✅ complete |
| **M3** | 移植 elrsV3.lua + lcd 绑定 | 参数界面显示 | ✅ complete |
| **M4** | 参数读写 (读/写射频参数) | 真机改 ELRS 模块参数 | ✅ complete |
| **M5** | RC 通道输出配置入口（src_cfg 源配置 + App 遥控页卡片） | 客户在遥控页配置通道/摇杆范围/开关值 | ✅ complete（固件 v1.6.18 + App v1.6.19，真机验证通过）|

---

## 六、M5: RC 通道输出配置入口（2026-08-15）

### 6.1 背景
V3s 输出 SBUS/CRSF 控制飞控。已有通道映射（rc_map）+ 输入源配置（src_cfg，feature/crsf-lua-bridge 分支移植，但固件未更新）。目标：客户在 DJI RC 遥控页直观配置输出通道。

### 6.2 固件端（v1.6.14）
- **src_cfg 系统**（rc_map.h/c）：`rc_src_cfg_t` 71 参数（摇杆 min/max/mid/rev + 开关触发值 + C12/DIR 档位）+ `rc_cfg_names` + `rc_cfg_defaults/sanitize/set_cfg` + `src_value` 应用
- **web_server**：Config 加 `rcSrcCfg`，读/存/API 响应 `src_cfg` + `src_cfg_names`，新增 `jsonHas/jsonObj`（深度匹配嵌套）
- **dji_rc**：`load_rc_output_cfg` 深度匹配 rc_output（cfg_json_obj）+ 应用 src_cfg（rc_map_set_cfg）
- **OTA 空间修复**：固件 tmpPath `/var/log`→`/tmp`（dji_rc.log 26MB 撑满 /var/log 导致 OTA write -1）

### 6.3 App 端（v1.6.16）
- **遥控页"通道配置"卡片**：输出协议（SBUS/CRSF）+ 预设（默认/AETR/TAER/自定义）+ 通道映射（CH1-16 选源）+ 输入源微调（分组可折叠）
- `SrcCfgRow`/`SRC_CFG_GROUPS`/`SrcCfgEditRow`/`SrcCfgGroup` 组件
- `apiPost` 加回调（保存成功/失败反馈）

### 6.4 验证状态
- ✅ 固件编译通过 + src_cfg API 保存（st1_min 1000→1100 读回成功）
- ✅ 固件 OTA v1.6.14 + App v1.6.16 部署
- ✅ 真机验证配置卡片交互（adb 点 USB 授权确认 → 遥控页）
- ✅ **bridge 模式 src_cfg 热重配修复**（v1.6.17，commit b865ca9）：反向/范围/映射运行中修改即时生效（值变了输出没变 → 根因 bridge 跳过热重配）
- ✅ **自锁修复**（v1.6.18，commit de235f2）：bridge 模式主循环推进 latch（out_send 被跳过导致 latch 永不 toggle）
- ✅ **低端点 900 显示修复**（App v1.6.19，commit de235f2）：ChannelScale 气泡独立 offset 定位不裁剪
- ✅ 真机确认：自锁 + 900 显示均正常（2026-08-15）
- ✅ **按键长按触发**（固件 v1.6.20 + App v1.6.23）：14 按键源加长按开关，按住 ≥500ms 才触发（防误触），仅独立按键源生效（复合源 C12/SHOT/DIR 不受影响）；入口在通道工作台每行"长按"开关
- ✅ **配置界面清理**（App v1.6.23）：删 RC 遥控器占位 + 通道映射编辑（遥控页已有），播放引擎/解码器合并组合下拉
- ⚠️ **自锁推进点回归**（2026-08-22 现场诊断，COM5 + adb 192.168.5.249）：当前板上 `good1=0`、`good2` 持续增长，说明有效 RC 帧来自第二路；`rec=1/stop=1` 能解码，CH8/CH13 会瞬时到 2000，但松手回 1000。根因不是配置或按键解码，而是非 bridge/SBUS 模式下 latch 仍依赖 P20 `out_send()` 推进，第一路无帧时永不 toggle。
  - **修复要求**：自锁 latch 由 `rc_merge` 后的统一 RC 状态推进一次；`write_state_file`、`send_rcmsg`、`out_send` 只应用当前 latch，不再各自推进，避免重复 toggle。
  - **验收**：默认映射下 `lock=...CH8/REC...CH13/STOP...` 时，按 REC 或 STOP 第一次应保持对应通道 2000，第二次按下解除回 1000；有效输入来自 P20 或 P0 都必须一致。
- ✅ **自锁验收通过（2026-08-22 晚）**：固件 **1.6.30 OTA 固化**（`backup/rootfs_v1630.squashfs`，dji_rc md5 `df32e70e`）。P20 路注入验收（ioctl UART1 MCR LOOP + DUML RC/0xAE 帧，`/tmp/inject_tty`）：
  - 按 REC 第一次 → ch8=**2000**（松手**保持不回落**，修复生效）→ 第二次按下 → ch8=**1000**（解除）
  - STOP toggle 2000↔1000 正常
  - P0 真实输入曾发 STOP=1（103 次）触发 ch13 保持 2000，P0 路自锁一致（老大确认 P20 验收已充分）

### 6.5 摇杆 CRSF 输出 + Lua 桥同时工作 — 调试记录（2026-08-16 进行中）

#### 需求
crsf 模式既要输出摇杆 CRSF（飞控控制），又要能配置 ELRS Lua（接收机页）。V3s UART0 同一串口。

#### 当前状态（进行中，未完成）
固件 v1.6.25（ringbuf 版）已在 V3s 运行，但 **Lua 配置未打通**——V3s 收到 Lua 命令但 ELRS 未响应。

#### 已确认的事实
1. **BOTHER 400000 在 V3s 实际输出 460800**（非 400k）：
   - 测试程序 BOTHER 设 400000 → 分频 div=11（理论上 400k）
   - 但用电脑 460800 采样能正确解析标准 CRSF（`C8 21 16` 摇杆帧），400000 采样乱码
   - **结论**：V3s UART0 实际波特率 460800（BOTHER 400000 被 8250 驱动映射到 460800 标准档）
   - 影响：400k 电脑桥乱码是**波特率不匹配**（V3s 460800 vs 电脑 400000），非固件 bug
2. **摇杆帧输出正常**（460800 采样）：
   - dji_rc `out ok/out enq mode=c`，COM30 抓到 999 帧全标准 0x16（RC_CHANNELS）
3. **V3s bridge 收到 Lua 命令**（App 在发）：
   - `bridge recv 451 次`（magic=CRSF），bridge fwd 转发到 UART0
4. **但 COM30 抓不到 Lua 帧**（只有 0x16 摇杆帧）→ **Lua 命令可能没实际发出，或 ELRS 收到但未响应**

#### 发送架构演进
- **v1.6.24 之前**：out_send（摇杆）直接写 UART0，bridge（Lua）直接写 UART0，用 g_out_write_mtx 互斥
  - 问题：摇杆帧高频（~500Hz）占满 UART0 TX，Lua 帧 O_NONBLOCK 写 EAGAIN 丢失 → ELRS 收不到 Lua 命令
- **v1.6.24（g_lua_tx_busy 方案）**：bridge 发 Lua 时置 busy 暂停摇杆
  - 问题：仍 EAGAIN（UART0 硬件曾卡死），且 busy 有竞态，已废弃
- **v1.6.25（ringbuf 方案，当前）**：摇杆帧 + Lua 帧统一入发送缓冲（`g_tx_ring` 4096B），主循环每 15ms 定时 `tx_flush` 批量写 UART0
  - 单一消费者写串口，无竞态
  - **现状**：摇杆帧正常入队+发送，但 Lua 帧未确认发出（COM30 只抓到 0x16）

#### 待解决问题（下一步）
1. **确认 Lua 帧是否真的被 tx_flush 发出**：可能 ringbuf 满被摇杆帧挤掉，或 Lua 帧发出但 ELRS 未响应
   - 需加 tx_flush 调试日志（记录发了多少字节/是否含 Lua 帧）
   - 或 ringbuf 里 Lua 帧优先（满时先丢摇杆帧）
2. **确认 ELRS 波特率匹配**：V3s 实际 460800，ELRS 需匹配（ELRS 支持 460800？）
3. **V3s 400k 需求**：老大要 400k，但 BOTHER 400000 实际 460800——需确认 ELRS 是否兼容 460800，或需内核级 400k 精确分频

#### 调试环境
- 电脑转发桥：COM10 ↔ COM30 互转（`tmp/_serial_bridge.py`）
  - COM30 连 V3s UART0，COM10 连 ELRS
  - **波特率 460800** 能正确解析 V3s 输出（400000 会乱码）
- 解析脚本：`tmp/_parse_crsf_frames.py`（识别 CRSF 帧类型）
- V3s UART0 波特率实际 460800（BOTHER 400000 映射）

#### 当前运行
- 固件 v1.6.25（ringbuf 版）在 V3s，dji_rc 输出 460800 8N1
- App v1.6.33

### 6.6 后续已知问题
- **DJI RC 上 adb 注入滚动不可靠**（swipe 回弹锁死）——调试环境限制，非产品 bug；可考虑把通道设置卡片入口前置

### 6.6 提交
`d5b3c02`（固件 src_cfg）· `ad62a0a`（App 卡片）· `ce0a316`（固件 v1.6.14 OTA 空间）· `0ef8426`（PRD 进度）
`b865ca9`（v1.6.17 热重配修复）· `de235f2`（v1.6.18 自锁 + App v1.6.19 900 显示）· `11a11d3`（文档）

## 五、风险

| 风险 | 缓解 |
|---|---|
| elrsV3.lua 依赖 EdgeTX API 多 | 先跑通核心 (crossfireTelemetryPush + lcd), 其余空实现 |
| Lua 脚本兼容性 | 用 LuaJ (Lua 5.2) 对齐 elrsV3 语法 |
| 网口转发延迟 | UDP 非阻塞, 参数操作低频, 延迟可接受 |
| ELRS 模块实际响应 | 需真机 ELRS 模块验证 (硬件) |

## 六、关键文件

- `ubuntu/src/dji_rc.cpp` — crsf-bridge 模式 (V3s)
- `ubuntu/src/crsf.h/c` — CRSF 编解码 (已实现)
- `android/...` — App Lua 引擎 + 绑定
- `docs/pb6_uart0_switch.md` — UART0 角色切换 (参考)
- `ax12 app/_rework/elrs_app/assets_elrsV3.lua.txt` — 移植的 Lua 脚本
## 2026-08-19 SC16IS752IPW V3s DTB 适配

### 硬件分配

- PB2: `NORMAL_RX_EN`
- PB3: `TX_BUS_EN`
- PB4: `CRSF_RX_EN`
- PB5: `SBUS_TX_EN`
- PB6/PB7: `TWI0_SCK/TWI0_SDA`，连接 SC16IS752IPW。
- UART0 固定作为 debug 串口；旧的 PB6 接地切换 debug/protocol 功能废弃。
- SC16IS752IPW `IRQ#` 当前版本不接，Linux `sc16is7xx` 驱动使用 polling。
- SC16IS752IPW `RESET#` 当前版本硬件默认上拉释放复位，设备树暂不声明 `reset-gpios`。
- I2C 地址按 EVT 板实测为 `0x4d`，晶振 `1.8432MHz`。

### DTB/内核适配

- `sun8i-v3s-licheepi-zero.dts`: 移除 `pb6_debug_pin`，`uart0` 只保留 `uart0_pb_pins`。
- `sun8i-v3s-licheepi-zero-dock.dts`: 启用 `&i2c0`，增加 `serial@4d`:

```dts
&i2c0 {
    status = "okay";

    sc16is752_uart: serial@4d {
        compatible = "nxp,sc16is752";
        reg = <0x4d>;
        clock-frequency = <1843200>;
    };
};
```

- `.config` 需要启用:
  - `CONFIG_I2C_MV64XXX=y`
  - `CONFIG_SERIAL_SC16IS7XX=y`
  - `CONFIG_SERIAL_SC16IS7XX_I2C=y`

### 已完成验证

- 已编译 `allwinner/sun8i-v3s-licheepi-zero-dock.dtb`。
- 已编译 `arch/arm/boot/zImage`，`sc16is7xx`、`sc16is7xx_i2c`、`i2c-mv64xxx` 均通过编译。
- 反编译读回确认 `serial@4d` 存在，`compatible = "nxp,sc16is752"`，`clock-frequency = <1843200>`。
- 反编译读回确认 PB6/PB7 为 `i2c0-pins`。
- 已复制到 `backup/sun8i-v3s-licheepi-zero-dock-sc16.dtb`，源 DTB 与备份 SHA256 相同。
- 已复制到 `backup/zImage_sc16`，源 zImage 与备份 SHA256 相同。

### 2026-08-20 SC16 地址修正

- EVT 板实测 SC16IS752 ACK 地址为 `0x4d`，旧 DTB 写成 `0x48`，导致内核只创建 `i2c 0-0048` 并停在 `deferred probe pending`。
- 已将 Linux DTS 源节点从 `serial@48/reg=<0x48>` 修正为 `serial@4d/reg=<0x4d>`。
- 已重编 `backup/sun8i-v3s-licheepi-zero-dock-sc16.dtb`，并更新 `backup/spi_image_sc16.bin` 内 `0x100000` 的 DTB 分区。
- 已新增 `scripts/verify_sc16_dtb.py`，用于反编译 DTB 并校验 `serial@4d`、`reg=<0x4d>`、`clock-frequency=<1843200>`，同时确认旧 `0x48` 不存在。

### 2026-08-20 SC16 晶振频率修正

- EVT 板实物 SC16IS752 晶振为 `1.8432MHz`，旧 DTB 写成 `14.7456MHz`，会导致 `sc16is7xx` 使用错误 `uartclk` 计算波特率。
- 已将 Linux DTS 源和备份 DTS 的 `clock-frequency` 从 `<14745600>` 修正为 `<1843200>`。
- 已更新 `scripts/verify_sc16_dtb.py`，反编译 DTB 时同时校验 `serial@4d`、`reg=<0x4d>`、`clock-frequency=<1843200>`。

### 下一步

- ✅ 打包带 `sc16is7xx`/I2C 驱动的新 kernel/rootfs（`backup/rootfs_sc16.squashfs` + `backup/spi_image_sc16.bin` + `backup/zImage_sc16`）。
- ✅ 修改 `dji_rc.cpp`，移除 PB6 debug 检测与运行中切换逻辑（`g_pb6_debug=false`，UART0 固定 debug）。
- ✅ 增加 PB2-PB5 模式控制（`aux_tmux_set` + `aux_tmux_apply`，启动 + 热重配时调用），**4 模式互斥（老大确认）**：
  - SBUS: `SBUS_TX_EN=1`，其他 0 → (0,0,0,1)
  - CRSF 发送: `TX_BUS_EN=1`，其他 0 → (0,1,0,0)
  - CRSF 接收: `CRSF_RX_EN=1`，其他 0 → (0,0,1,0)
  - 全双工: `TX_BUS_EN=1, NORMAL_RX_EN=1`，其他 0 → (1,1,0,0)
  - **CRSF 半双工时分切换**：基线接收态 (0,0,1,0)；每次发帧 `tx_write_uart` 切 TX (0,1,0,0)，
    帧发完（`uart_drain_tx` 轮询 TIOCOUTQ=0）切回 RX (0,0,1,0)。回传响应（crsf_rx_thread）统一走 tx_write_uart。
- 固件版本递增 + 固化：待 EVT 板真机验证 SC16 后统一处理（当前固件 F 版本仍 1.6.29）。
