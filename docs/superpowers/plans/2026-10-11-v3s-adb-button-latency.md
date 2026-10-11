# V3S ADB Button Latency Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make V3S ADB button edges wake the RCMSG path and Android UI immediately while retaining 50Hz axis pacing and ordered DOWN/UP delivery.

**Architecture:** Two condition-variable generation gates remove the two V3S 20ms phase waits without turning the stable axis path into a busy loop. Android reports edge packets separately from its latest-only pump and transfers them through a bounded coroutine Channel to the Compose main thread.

**Tech Stack:** C++17, pthread/`std::condition_variable`, Kotlin, kotlinx.coroutines Channel, Jetpack Compose, CMake/CTest, Gradle.

---

### Task 1: Android immediate edge extraction

**Files:**
- Modify: `android/app/src/test/java/com/tunnathub/app/RcMsgUiPumpTest.java`
- Modify: `android/app/src/main/java/com/tunnathub/app/RcMsgUiPump.kt`
- Modify: `android/app/src/main/java/com/tunnathub/app/MainActivity.kt`

- [ ] Add a test expecting `notePacket(packet, edgeKey)` to return `null` for the baseline and the exact packet for DOWN and UP changes.
- [ ] Run `RcMsgUiPumpTest` and confirm compilation fails because `notePacket` currently returns `Unit`.
- [ ] Change the overload to return `T?`, preserving the existing bounded FIFO, and add a capacity-32 `Channel<RcMsg.Data>` in `MainActivity`.
- [ ] On a returned edge call `trySend`; collect the Channel on the main coroutine and call `applyRcData` only in V3S RCMSG modes.
- [ ] Run Android unit compilation and `RcMsgUiPumpTest`; expect PASS.

### Task 2: V3S generation wake gate

**Files:**
- Create: `ubuntu/src/rc_event_gate.h`
- Create: `ubuntu/src/rc_event_gate.cpp`
- Create: `ubuntu/tests/rc_event_gate_test.cpp`
- Modify: `ubuntu/CMakeLists.txt`
- Modify: `ubuntu/src/dji_rc.cpp`

- [ ] Add a test proving `notify()` advances a generation, `waitUntil()` returns immediately for a newer generation, times out otherwise, and wakes when stopped.
- [ ] Add the test target and run it; confirm failure because `RcEventGate` does not exist.
- [ ] Implement `RcEventGate` with a mutex, condition variable, monotonically increasing generation and stop flag.
- [ ] Replace the ADB publisher `usleep(20000)` with a 20ms gate wait; notify it after accepted getevent/40007 data.
- [ ] Replace the main-loop `nanosleep` with a 20ms gate wait; notify it when ADB publishing popped at least one button edge.
- [ ] Stop both gates before joining threads and run CTest; expect all tests PASS.

### Task 3: Version, build, review, and deployment

**Files:**
- Modify: `android/app/build.gradle.kts`
- Modify: `ubuntu/src/web_server.cpp`
- Create: `backup/release_<timestamp>_v1.6.85/manifest.txt`
- Modify: `C:/Users/xlong/Documents/Obsidian Vault/00_收件箱/2026-10-11-v3s-rc-input-mode-control.md`

- [ ] Set Android and V3S version to `1.6.85`, then build all Ubuntu targets and Android debug APK.
- [ ] Run CTest, Android unit tests, `git diff --check`, and code review focused on lost wakeups, shutdown, edge duplication, and thread safety.
- [ ] Commit source changes as `perf(protocol): wake RC button path on edges`.
- [ ] Build timestamped rootfs, SPI and APK artifacts; generate manifest with commit, branch, sizes, SHA256 and purpose; read back every hash and inspect rootfs/SPI/APK metadata.
- [ ] OTA V3S, install APK through V3S network ADB, reboot, and read back both versions.
- [ ] Verify `rc_input_mode=v3s_adb`, `active_src=v3s_adb_rc`, RCMSG remains above 40Hz, and button DOWN/UP reaches Android without fixed hold.
- [ ] Update and read back the knowledge note with the event-driven latency design.
