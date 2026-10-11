# V3s ADB Button Edge Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 V3s 与 Android 两端按顺序传递按下和释放边沿，并接入 event3 的 L1-R3 按键。

**Architecture:** getevent 和 40007 接收线程按变化顺序写入边沿队列，发布线程逐项消费；Android UI pump 使用同样的边沿队列。稳定轴状态仍采用最新值。

**Tech Stack:** C++17、CMake、TCP ADB、DUML、RCMSG

---

### Task 1: Expand getevent key mapping

**Files:**
- Modify: `ubuntu/src/adb_getevent_rc.cpp`
- Modify: `ubuntu/tests/adb_getevent_rc_test.cpp`

- [ ] 增加 event3 `KEY_F1..F6` 的失败测试并运行，确认当前解析失败。
- [ ] 扩展按键解析和 L1..R3 映射；空设备过滤参数表示接受所有已知按键设备。
- [ ] 运行 `adb_getevent_rc_test`，确认全部通过。

### Task 2: Queue edges before fusion

**Files:**
- Modify: `ubuntu/src/adb_rc_fusion.h`
- Modify: `ubuntu/src/adb_rc_fusion.cpp`
- Modify: `ubuntu/src/dji_rc.cpp`
- Modify: `ubuntu/tests/adb_rc_fusion_test.cpp`

- [ ] 增加同一发布周期内按下后抬起仍输出高电平的失败测试。
- [ ] 建立容量 32 的边沿队列，并覆盖 21 个 RCMSG 按键位。
- [ ] 在 getevent/40007 接收入口记录边沿，发布前按顺序取出，再融合。
- [ ] Android UI pump 对按键边沿顺序消费，稳定轴帧仍只取最新值。
- [ ] 运行两个 ADB RC 单测和完整 CMake 构建。

### Task 3: Release and deploy

**Files:**
- Modify: `ubuntu/src/web_server.cpp`
- Create: `backup/release_<timestamp>_v1.6.84/manifest.md`

- [ ] 版本提升到 `1.6.84`，构建带时间戳 rootfs、SPI 镜像和 APK。
- [ ] 校验 SHA256、SquashFS 内容、SPI rootfs 切片和 manifest。
- [ ] OTA 部署并读回版本、启动分区、输入模式以及 RC 运行频率。
- [ ] 审查最终差异并提交代码。
