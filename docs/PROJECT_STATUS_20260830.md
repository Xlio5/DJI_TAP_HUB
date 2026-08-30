# TUN_NAT_HUB 项目进度与计划

> 更新日期: 2026-08-30
> 本文件汇总当前进度、已完成功能、版本历史、待办计划与部署经验。

---

## 一、当前状态

| 项目 | 状态 |
|---|---|
| **固件** | **F1.6.53**（`backup/rootfs_v1653.squashfs`，md5 `400fd87b…`，已 OTA 部署）|
| **App** | **1.6.67 诊断版**（正式功能在 1.6.66，含临时诊断日志 LRDiag/RcCodec 待清理）|
| **硬件** | DJI RC Plus 2（rc701）+ V3s（172.20.10.3 电脑直连 / 192.168.144.66 RC 隧道）|
| **git** | 分支 `codex/sc16-remote-test`，最近 push `c943aee`（1.6.66）|

---

## 二、已完成功能

### 1. Shizuku 集成 — 高频 getevent（App 1.6.58）
- 集成 `rikka.shizuku` **13.1.0**（newProcess 仍 public，13.1.1+ 转 private）
- Manifest：`ShizukuProvider`(com.tunnathub.app.shizuku) + `API_V23` 权限 + `V3_SUPPORT` + **`<queries>` 包可见性**
- `ShizukuGetEventReader` 以 shell 身份跑 `getevent`，真机摇杆从 adb 的 **—Hz → 64Hz**
- 参考 App：`app参考/rc_20260413171213.apk`、`shizuku-v13.6.0…apk`

### 2. 双源速率显示（App 1.6.57）
- 遥控页 header 显示 `getevent XHz · 40007 YHz`
- `RcFusionRuntime` 统计两源到达速率（指数平滑 + 老化归零）

### 3. L1~R3 = APM 6档互斥自锁（App 1.6.62 / 固件 1.6.53）
- **App**：getevent `KEY_F1..F6`→L1..R3（**按键在 event3 gpio-keys，不在 event4 摇杆** → reader 读所有设备，摇杆 ABS 轴仍只认 event4）；RCM1 buttons **bit 15-20** 编码
- **固件**：`rc_state_t` 加 l1..r3；`SRC_LR` 复合源；`update_lr_latch` 按下沿互斥切档（松开保持自锁）
- **根因修复**：固件主循环加 `advance_output_latches`（App 融合路径之前不推进 latch → lr_pos 恒 0）
- 真机验证（sendevent 注入）：L1→0/1000、L2→1/1200、L3→2/1400、R1→3/1600、R2→4/1800、R3→5/2000

### 4. 40007 按键融合到 CH（App 1.6.63）
- **根因**：`fuse` 里 `rec = geKeys?.rec ?: keys?.rec`，getevent 活跃时 rec=0 非 null 覆盖 40007 的 REC → CH8 不反映
- **修复**：rec/shot 改 **OR 合并** `(geKeys?.x ?: 0) or (keys?.x ?: 0)`
- `PORT40007_FRESH_MS` 3000→**5000ms**（覆盖 40007 服务端 ~4s 断 TCP 周期）
- `ShizukuGetEventReader` 改回 `getevent` 读所有设备（**getevent 只接受单 device 参数**，多参数报错退出 → reader 反复重建）
- 真机验证：按摇杆 REC → 固件 rec=1、ch8=2000

### 5. 遥控页按键区显示 L1~R3（App 1.6.65）
- `RcMsg.Data` 加 l1..r3 字段（RcMsg.parse 解析 bit 15-20）
- `applyRcData` 更新 rcL1..rcR3
- `ButtonStatusGrid` 加 L1/L2/L3/R1/R2/R3 chip（ON/OFF）

### 6. L1~R3 按住保持 ON（App 1.6.66）
- **根因**：fuse 里 `l1 = geKeys?.l1`（geKeys 依赖 80ms fresh），getevent KEY 边沿触发，按住无事件 → 80ms 后 geKeys=null → l1 被清 0
- **修复**：l1..r3 改用 `getevent?.l1`（不依赖 fresh，getevent keys 状态锁存）
- 验证：sendevent 保持 L1 → 固件 l1=1 持续 6s

### 7. 固件回传更新遥控页 CH7-16（App 1.6.64）
- 固件回传（65530）的 CH7-16 更新遥控页通道显示（按键/模式/拨轮映射后的实际值）
- CH1-6 摇杆仍用本地融合即时（避免回传延迟）
- 验证：遥控页 CH16=1400（固件 lr 值）显示正常

---

## 三、版本历史

### App
| 版本 | 内容 |
|---|---|
| 1.6.57 | 遥控页双源速率显示 |
| 1.6.58 | Shizuku 集成（getevent 64Hz）|
| 1.6.59 | L1~R3 编码初版（bit 15-20）|
| 1.6.60 | Shizuku 自愈 + 40007 快速重连 |
| 1.6.61 | getevent 读所有设备（按键在 event3）|
| 1.6.62 | 正式版（清理诊断日志）|
| 1.6.63 | 40007 按键融合到 CH（rec/shot OR 合并）|
| 1.6.64 | 固件回传更新 CH7-16 |
| 1.6.65 | 按键区显示 L1~R3 |
| 1.6.66 | L1~R3 按住保持 ON |
| 1.6.67+ | 诊断版（LRDiag/RcCodec 日志，**临时**）|

### 固件
| 版本 | 内容 |
|---|---|
| 1.6.50 | SRC_LR 复合源 + bit15-20 解析 |
| 1.6.51/1.6.52 | 诊断（l1..r3 显示 / rx_buttons）|
| 1.6.53 | **主循环 advance_output_latches（L1~R3 latch 生效）** 正式 |

---

## 四、当前卡点（进行中）

### 物理按键 vs sendevent 注入差异
- **现象**：sendevent 注入 L1/R1 → 固件 `lr_pos` 正常切换（0/3 → ch16 1000/1600）；**物理按 L1（14:58）App 收到 KEY_F1（LRDiag 日志），但固件 l1=0**，lr_pos 不切
- **已确认**：
  - App 采样/编码/固件 latch 链路（sendevent 路径）完全正常
  - 物理 L1 的 getevent 事件 = event3 KEY_F1 DOWN（和 sendevent 相同 code）
  - 40007 的 AE 帧 stop 位全 0（STOP 不走 40007）
- **待确认**：物理按键时 `sample.l1` 到底是多少（新版日志已加 `keys.L1 / sample.l1`，需老大按 L1 触发一次观察）
- **可能方向**：
  1. 物理事件 value/时序差异（repeat value=2 等）
  2. keys 设置或 sample 覆盖问题
  3. 物理按键瞬时（DOWN 后无事件，latestGetevent 更新时机）

### 待办清单
- [ ] **确认物理按键采样**（老大按 L1 + LRDiag 日志 `keys.L1/sample.l1`）
- [ ] 修复物理按键问题（若存在）
- [ ] **清理诊断日志**（LRDiag/RcCodec），出正式版（1.6.68）
- [ ] 完整验证（物理按键 + 通道映射 + 自锁/互斥）
- [ ] SESSION_HANDOFF 文档同步
- [ ] commit + push

---

## 五、部署经验

- **OTA 经 RC↔V3s VPN 隧道传 3.8MB 极不稳定**（curl 常 exit 56/超时，已 3 次失败、2 次导致 V3s 变砖，靠双槽回退恢复）
- **最稳方式：电脑直连 V3s（172.20.10.3:8080）curl OTA**（一次成功）
- V3s 双槽：OTA 写 inactive 槽，重启切换；起不来时 U-Boot 回退旧槽
- 固件重建：WSL 20.04 `bash tmp/_rebuild_rootfs_v16XX.sh`（buildroot 工具链 + mksquashfs，rootfs <4MB OTA 限制）

---

## 六、关键文件

| 模块 | 文件 |
|---|---|
| App 融合 | `android/…/rc/RcFusionEngine.kt`、`RcFusionRuntime.kt`、`RcMsgCodec.kt` |
| App getevent | `android/…/rc/ShizukuGetEventReader.kt`、`GetEventRcReader.kt` |
| App 协议 | `android/…/RcMsg.kt`（Data 加 l1..r3）|
| App UI | `android/…/MainActivity.kt`（按键区 L1~R3、通道显示）|
| App 服务 | `android/…/service/TunNatVpnService.kt` |
| 固件 | `ubuntu/src/dji_rc.cpp`、`rc_map.c/h`、`rc_decode.h`、`web_server.cpp` |
