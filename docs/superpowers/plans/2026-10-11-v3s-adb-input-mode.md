# V3s ADB RC Input Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add persisted Android fusion, V3s serial, and V3s network ADB RC input modes, selectable from the Android App and enforced by V3s.

**Architecture:** The SPI JSON field `rc_input_mode` is authoritative. `web_server` exposes it over HTTP, while the integrated `dji_rc` hot-reloads it and strictly selects one already-running collector without cross-source fallback. Android commits its local mode only after the V3s API accepts the change.

**Tech Stack:** C++17, CMake, BusyBox init, SPI JSON config, Kotlin, Jetpack Compose, coroutines, Gradle/JVM tests.

---

### Task 1: V3s Input-Mode Core

**Files:**
- Create: `ubuntu/src/rc_input_mode.h`
- Create: `ubuntu/src/rc_input_mode.cpp`
- Create: `ubuntu/tests/rc_input_mode_test.cpp`
- Modify: `ubuntu/CMakeLists.txt`
- Modify: `ubuntu/src/dji_rc.cpp`

- [ ] **Step 1: Write the failing C++ test**

Test `parse_rc_input_mode()` for the three wire values and invalid/missing fallback to `V3sAdb`; test `select_rc_input()` with fresh and stale Android, serial, and ADB states and assert no cross-source fallback.

- [ ] **Step 2: Run the test target and verify RED**

Run `cmake --build ubuntu/build-codex-adb-armv7-fresh --target rc_input_mode_test -j2`.
Expected: fail because the target and API do not exist.

- [ ] **Step 3: Implement the mode parser and strict selector**

Define `enum class RcInputMode { AndroidFusion, V3sSerial, V3sAdb };`, `parse_rc_input_mode(std::string_view)`, `rc_input_mode_name()`, and a selector returning the selected source only when its freshness predicate is true.

- [ ] **Step 4: Integrate SPI load and hot reload into dji_rc**

Read top-level `rc_input_mode` alongside the existing SPI `rc_output` configuration. Preserve CLI flags as startup fallback, publish `configured_input_mode`, and make selection/output/RCMSG use the strict selector.

- [ ] **Step 5: Verify GREEN and regression build**

Run the new host test, existing ADB tests, `python scripts/test_v3s_debug_baseline.py`, and the ARM `dji_rc` build. Expected: all executable tests pass and ARM link succeeds.

- [ ] **Step 6: Commit**

Commit as `feat(ubuntu): add persisted RC input modes`.

### Task 2: V3s Control API

**Files:**
- Modify: `ubuntu/src/web_server.cpp`
- Create: `ubuntu/tests/rc_input_api_test.cpp`
- Modify: `ubuntu/CMakeLists.txt`

- [ ] **Step 1: Write failing API/config tests**

Cover default `v3s_adb`, JSON load/save round-trip, all three valid values, rejection of an invalid value, and `/api/config` serialization.

- [ ] **Step 2: Run and verify RED**

Build/run `rc_input_api_test`; expected failure because `Config::rcInputMode` and API helpers are absent.

- [ ] **Step 3: Implement persistence and routes**

Add `Config::rcInputMode`, serialize it at top level, expose `GET /api/rc/input`, and implement `POST /api/rc/input` returning HTTP 400 for invalid values and saving SPI only after validation.

- [ ] **Step 4: Verify GREEN and web_server build**

Run the API test and ARM `web_server` build. Use `git diff --check`.

- [ ] **Step 5: Commit**

Commit as `feat(ubuntu): expose RC input mode API`.

### Task 3: Android Three-Mode State and Client

**Files:**
- Modify: `android/app/src/main/java/com/tunnathub/app/RcInputMode.kt`
- Create: `android/app/src/main/java/com/tunnathub/app/RcInputModeClient.kt`
- Modify: `android/app/src/main/java/com/tunnathub/app/service/TunNatVpnService.kt`
- Modify: `android/app/src/test/java/com/tunnathub/app/RcInputModeTest.java`
- Create: `android/app/src/test/java/com/tunnathub/app/RcInputModeClientTest.java`

- [ ] **Step 1: Extend failing mode tests**

Assert parsing for `v3s_serial` and `v3s_adb`, full-channel UDP consumption for both V3s modes, Android fusion only for `android_fusion`, and distinct status strings.

- [ ] **Step 2: Write failing client state test**

Use an injected transport to prove local state commits only on a successful V3s response and remains unchanged on timeout or HTTP failure.

- [ ] **Step 3: Run JVM tests and verify RED**

Run `android/gradlew.bat :app:compileDebugUnitTestJavaWithJavac --no-daemon`; expected compile/test failure from missing enum/client behavior.

- [ ] **Step 4: Implement enum, pure transition logic, and HTTP client**

Add `V3S_SERIAL` and `V3S_ADB`, make `usesAndroidFusion` and `usesV3sRcMsg` explicit properties, and implement GET/POST against `http://192.168.144.66:8080/api/rc/input` on `Dispatchers.IO`.

- [ ] **Step 5: Update service lifecycle**

Run local fusion only when `usesAndroidFusion`; pause it for both V3s modes and preserve UDP 65530 reception.

- [ ] **Step 6: Verify GREEN**

Compile and run the focused JVM test mains. Expected: all assertions pass.

- [ ] **Step 7: Commit**

Commit as `feat(android): model three RC input modes`.

### Task 4: Android UI and Status

**Files:**
- Modify: `android/app/src/main/java/com/tunnathub/app/MainActivity.kt`
- Modify: `android/app/src/main/java/com/tunnathub/app/RcInputMode.kt`
- Modify: `android/app/build.gradle.kts`

- [ ] **Step 1: Add failing status-text tests**

Assert Android, serial, and ADB status formats, including ADB event and rcmsg rates.

- [ ] **Step 2: Implement the three-option segmented control**

Render “安卓融合”, “V3s 串口”, and “V3s ADB”. On click, enter a pending state, POST to V3s, then commit preference/restart fusion on success or show a compact failure message without changing mode.

- [ ] **Step 3: Synchronize authoritative mode on VPN connection**

Parse `rc_input_mode` from `/api/config`, update preference and service runtime, and add `adb_ge_hz` parsing from `/api/rc` for the ADB status line.

- [ ] **Step 4: Bump Android version and verify**

Increment versionCode/versionName, run focused tests and `:app:assembleDebug --no-daemon`.

- [ ] **Step 5: Commit**

Commit as `feat(android): add V3s ADB mode control`.

### Task 5: Release, Deploy, and End-to-End Verification

**Files:**
- Modify generated rootfs staging only through existing build scripts.
- Create: `backup/release_<timestamp>_<version>/manifest.txt`
- Create: timestamped APK and V3s rootfs/OTA artifacts in the same release directory.

- [ ] **Step 1: Build versioned Android and V3s artifacts**

Use existing clean rootfs/OTA scripts so the new `dji_rc`, `web_server`, and `S99tun_nat_hub` enter squashfs. Name every artifact with version and timestamp.

- [ ] **Step 2: Create and read back the manifest**

Record branch, commit, sizes, SHA256 values, and intended partitions/uses. Recompute hashes after copying.

- [ ] **Step 3: Deploy APK over the independent available ADB transport**

Install, launch, confirm version, and avoid relying on an App-owned transport if installation would tear it down.

- [ ] **Step 4: Deploy V3s OTA/rootfs and verify readback**

Use the existing OTA path, verify the flashed slot/hash or extracted squashfs contents, then reboot once.

- [ ] **Step 5: Exercise all three modes**

For each mode, verify App selection, `/api/config`, `/tmp/rc_state.json`, process logs, and UDP rate. Confirm strict no-fallback behavior by observing inactive-source data does not change output.

- [ ] **Step 6: Verify unattended V3s ADB boot**

Leave `v3s_adb` selected, stop the App Activity, reboot V3s, and verify ADB connection, `active_src=v3s_adb_rc`, and approximately 50Hz RCMSG when the VPN endpoint is present.

- [ ] **Step 7: Review and commit release metadata**

Run `git diff --check`, inspect only task-owned changes, commit release metadata if tracked, and report unrelated dirty files without altering them.
