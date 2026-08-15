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

### 6.5 后续已知问题
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
