# getevent 摇杆频率 10-14Hz 根因分析 (2026-08-29)

## 问题现象

摇杆快速推动时，App 遥控页显示的实时频率仅 **10-14Hz**，预期 **60Hz**（getevent 原始事件间隔 14-16ms）。

## 根因

**adbd 的 TCP transport（5555）无法转发 getevent 输出，只有 USB transport 正常。**

App 的 `AdbGetEventReader` 通过 `127.0.0.1:5555`（loopback TCP）连本机 adbd 执行 getevent。链路握手全部正常：

- `socket 连接` → `CNXN 握手` → `OPEN shell` → `OKAY` 全成功
- 设备上 `getevent` 进程也在正常运行（阻塞在 `do_sys_poll` 等 event4 事件）

但 adbd 就是不通过 TCP 转发 getevent 的 WRTE 数据，App 永远读不到摇杆事件。这是 DJI 设备 adbd 定制 / Android 11 adbd 的 bug。

## 证据（对比测试）

| 方式 | 结果 |
|---|---|
| 电脑 adb **USB** 读 event4 | ✅ 60Hz（14-16ms）|
| 电脑 adb **TCP 5555** 读 event4 | ❌ 空 |
| App 走 **127.0.0.1:5555**（loopback TCP）| ❌ 空 |

## 影响

App 读不到 getevent，`RcFusionEngine` 融合引擎回落到 **40007 端口**（V3s 回传），而 40007 的频率就是 10-14Hz —— 这就是界面显示的频率。

## 解决方案

改用 **Shizuku 直读 getevent**：Shizuku 给 App 授予 shell 权限后，App 直接 `ProcessBuilder` 执行 getevent、读本地管道（不走 adbd TCP），拿到 60Hz。

- App 已有现成的 `GetEventRcReader`（ProcessBuilder 读 getevent 的旧实现，见 `rc/GetEventRcReader.kt`）
- 需要：集成 Shizuku API + 请求授权 + 改走 Shizuku shell
- 代价：设备重启后需重新启动 Shizuku 服务

## 附带修复：满杆 1822 → 2000

同轮修复了满杆通道值 1822→2000（提交 `adbee08`）：

- **根因**：App 轴范围用 ±1024 缩放，固件 `chmap.c` 用 ±660，满杆 660 → `1500+660*500/1024=1822` 而非 `1500+660*500/660=2000`
- **修复**：全链路轴范围统一 ±660（`rawToUs /660`、clamp ±660、getevent `×660/32768`）
- **版本**：App 1.6.54 → 1.6.56

## 相关文件

- `android/.../rc/AdbGetEventReader.kt` — adb TCP 读 getevent（此方案已确认不可用）
- `android/.../rc/GetEventRcReader.kt` — ProcessBuilder 读 getevent（Shizuku 方案的基础）
- `ubuntu/src/chmap.c` — 固件 ±660 通道映射（`map_stick: 1500 + v*500/660`）
- `ubuntu/src/rc_decode.c` — 固件 DUML 0xAE 解码（`raw - 1024`，满杆 ±660）
