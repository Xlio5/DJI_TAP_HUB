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

| 阶段 | 内容 | 验证 |
|---|---|---|
| **M1** | V3s crsf-bridge 模式 (UART0↔网口转发) | 网口 echo CRSF 帧 |
| **M2** | App 集成 LuaJ + crossfireTelemetryPush 绑定 | App 能跑简单 Lua |
| **M3** | 移植 elrsV3.lua + lcd 绑定 | 参数界面显示 |
| **M4** | 参数读写 (读/写射频参数) | 真机改 ELRS 模块参数 |

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
