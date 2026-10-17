# RC Stick Visualizer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Android 遥控页面增加使用 RH/RV/LV/LH 原始通道驱动的紧凑型左右摇杆可视化。

**Architecture:** 将原始值归一化提取为无 Android 依赖的 `RcStickPosition` 纯计算对象，供 JVM 单元测试覆盖边界和方向。Compose 在现有 `RcPanelContent` 内使用 Canvas 绘制固定尺寸底座、中心线和杆头，并继续保留原通道网格。

**Tech Stack:** Kotlin, Jetpack Compose Canvas, JUnit 4, Gradle

---

### Task 1: 摇杆位置纯计算

**Files:**
- Create: `android/app/src/main/java/com/tunnathub/app/RcStickPosition.kt`
- Create: `android/app/src/test/java/com/tunnathub/app/RcStickPositionTest.java`

- [ ] **Step 1: 写失败测试**

测试零点、满量程限制，以及 `raw_ch1..4` 到左右杆轴的语义映射。

- [ ] **Step 2: 确认测试失败**

Run: `cd android && ./gradlew testDebugUnitTest --tests com.tunnathub.app.RcStickPositionTest`

Expected: FAIL，因为 `RcStickPosition` 尚不存在。

- [ ] **Step 3: 实现最小计算逻辑**

新增不可变位置数据和 `fromRawChannels()`，量程固定为 660，输出限制到 `[-1f, 1f]`。

- [ ] **Step 4: 确认测试通过**

Run: `cd android && ./gradlew testDebugUnitTest --tests com.tunnathub.app.RcStickPositionTest`

Expected: BUILD SUCCESSFUL。

### Task 2: Compose 紧凑双摇杆区

**Files:**
- Modify: `android/app/src/main/java/com/tunnathub/app/MainActivity.kt`

- [ ] **Step 1: 添加固定尺寸 Canvas 摇杆组件**

绘制圆形底座、十字中心线、中心点和青色杆头，并在下方显示轴名及原始值。

- [ ] **Step 2: 接入遥控页面**

在模式/状态之后、`SBUS CH1-CH16` 之前插入双列紧凑区；左杆传入 LH/LV，右杆传入 RH/RV。

- [ ] **Step 3: 构建验证**

Run: `cd android && ./gradlew testDebugUnitTest assembleDebug`

Expected: BUILD SUCCESSFUL。

### Task 3: 版本、发布归档和审查

**Files:**
- Modify: `android/app/build.gradle.kts`
- Create: `backup/release_<timestamp>_v1.6.97/manifest.txt`
- Create: `backup/release_<timestamp>_v1.6.97/tun_nat_hub_android_v1.6.97_<timestamp>.apk`

- [ ] **Step 1: 升级版本**

将 `versionCode` 升至 127、`versionName` 升至 `1.6.97`。

- [ ] **Step 2: 归档并读回校验**

复制 APK 到带版本和时间戳的 release 目录，生成包含 commit、分支、大小、用途和 SHA256 的 manifest，并重新计算归档 APK SHA256 对比。

- [ ] **Step 3: 代码审查与提交**

检查坐标方向、范围限制、Compose 重组成本、布局溢出和测试覆盖，只提交本轮相关文件。

