# 40007 Direct Button Edge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Send each decoded 40007 button transition directly as RCMSG in `v3s_adb` mode, without waiting for the ADB publisher or main loop.

**Architecture:** Add a reusable button-state tracker beside the existing fusion helpers, then use it in the 40007 receive thread to detect edges without queueing them. The receive thread copies source state under the mutex, fuses and sends after unlocking, while the existing 50Hz path remains the authoritative periodic state publisher.

**Tech Stack:** C++17, POSIX UDP sockets, CMake/CTest, Buildroot ARMv7 cross-build, Android Kotlin receiver already in place.

---

### Task 1: Add queue-free button edge tracking

**Files:**
- Modify: `ubuntu/src/adb_rc_fusion.h`
- Modify: `ubuntu/src/adb_rc_fusion.cpp`
- Modify: `ubuntu/tests/adb_rc_fusion_test.cpp`

- [ ] **Step 1: Write the failing tracker tests**

Add tests that initialize `AdbRcButtonTracker`, confirm the initial state is not an edge, confirm a C3 press is an edge, confirm the repeated pressed state is not an edge, and confirm release is an edge. The test must call the new API:

```cpp
AdbRcButtonTracker tracker{};
expectEq(adb_rc_track_button_change(&tracker, &released), false,
         "initial state establishes baseline");
expectEq(adb_rc_track_button_change(&tracker, &pressed), true,
         "press is an edge");
expectEq(adb_rc_track_button_change(&tracker, &pressed), false,
         "same state is not repeated");
expectEq(adb_rc_track_button_change(&tracker, &released), true,
         "release is an edge");
```

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
wsl bash -lc 'cd /mnt/c/my_project/TUN_NAT_HUB && cmake -S ubuntu -B ubuntu/build-wsl-button-direct && cmake --build ubuntu/build-wsl-button-direct --target adb_rc_fusion_test -j2'
```

Expected: compilation fails because `AdbRcButtonTracker` and `adb_rc_track_button_change` do not exist.

- [ ] **Step 3: Implement the tracker**

Declare a tracker containing only the last state and `has_last`. Implement `adb_rc_track_button_change()` by reusing the existing full button-field comparison. It updates the baseline on every call and returns true only for a real transition after initialization.

- [ ] **Step 4: Run focused and full host tests**

Run:

```powershell
wsl bash -lc 'cd /mnt/c/my_project/TUN_NAT_HUB && cmake --build ubuntu/build-wsl-button-direct -j2 && ctest --test-dir ubuntu/build-wsl-button-direct --output-on-failure'
```

Expected: all CTest tests pass.

- [ ] **Step 5: Commit the tracker**

```powershell
git add ubuntu/src/adb_rc_fusion.h ubuntu/src/adb_rc_fusion.cpp ubuntu/tests/adb_rc_fusion_test.cpp
git commit -m "feat(ubuntu): track 40007 button edges without queueing"
```

### Task 2: Send 40007 edges directly

**Files:**
- Modify: `ubuntu/src/dji_rc.cpp`
- Modify: `ubuntu/tests/adb_rc_fusion_test.cpp`

- [ ] **Step 1: Write the failing fast-path eligibility test**

Add a small pure helper to the fusion module or existing input-mode module and test these cases before implementation:

```cpp
expectEq(adb_rc_should_send_direct_edge(true, true, true), true,
         "active v3s adb edge is sent directly");
expectEq(adb_rc_should_send_direct_edge(false, true, true), false,
         "unchanged buttons do not send");
expectEq(adb_rc_should_send_direct_edge(true, false, true), false,
         "inactive input mode does not send");
expectEq(adb_rc_should_send_direct_edge(true, true, false), false,
         "invalid socket does not send");
```

- [ ] **Step 2: Run the focused test and verify RED**

Run the `adb_rc_fusion_test` target. Expected: compilation fails because the eligibility helper is missing.

- [ ] **Step 3: Implement direct edge transmission**

In `adb_40007_thread`:

1. Merge and store the incoming 40007 state under `g_mtx`.
2. Detect the edge with `AdbRcButtonTracker` instead of `g_adb_40007_edge_queue`.
3. Copy current getevent state, timestamps, and connection state while locked.
4. Release `g_mtx`, calculate source ages, and call `adb_rc_fuse()`.
5. Re-read `g_rc_input_mode`; if it is `V3sAdb`, the fused state is valid, and `g_rcmsg_fd` is valid, allocate an atomic sequence and call `send_rcmsg()` immediately.
6. Keep `g_adb_publish_gate.notify()` for prompt periodic-state convergence, but remove 40007 queue popping from `adb_rc_publish_thread`.

The fast path must not call `advance_output_latches()` and must not hold `g_mtx` during `sendto()`.

- [ ] **Step 4: Add latency counters and JSON fields**

Record successful direct sends, failures, last decode-to-send duration, and maximum duration in atomics. Expose them as `adb_40007_edge_tx_count`, `adb_40007_edge_tx_us`, `adb_40007_edge_tx_max_us`, and `adb_40007_edge_tx_err` from `write_state_file()`.

- [ ] **Step 5: Run all Ubuntu tests and build**

Run:

```powershell
wsl bash -lc 'cd /mnt/c/my_project/TUN_NAT_HUB && cmake --build ubuntu/build-wsl-button-direct -j2 && ctest --test-dir ubuntu/build-wsl-button-direct --output-on-failure'
```

Expected: build succeeds and all tests pass.

- [ ] **Step 6: Commit the fast path**

```powershell
git add ubuntu/src/dji_rc.cpp ubuntu/src/adb_rc_fusion.h ubuntu/src/adb_rc_fusion.cpp ubuntu/tests/adb_rc_fusion_test.cpp
git commit -m "perf(ubuntu): send 40007 button edges directly"
```

### Task 3: Build, package, deploy, and verify

**Files:**
- Modify: version metadata used by the V3S release build
- Create: `backup/release_<timestamp>_v1.6.86/manifest.txt`
- Create: timestamped V3S rootfs and SPI artifacts in the release directory

- [ ] **Step 1: Cross-build the V3S binary**

Use the existing ARMv7 Buildroot toolchain and release scripts that produced v1.6.85. Verify the resulting `dji_rc` architecture and execute its self-test where supported.

- [ ] **Step 2: Package v1.6.86 artifacts**

Create `backup/release_<YYYYMMDD_HHMMSS>_v1.6.86/`, store timestamped rootfs/SPI artifacts, and generate a manifest containing version, timestamp, branch, source commit, purpose, size, and SHA256 for every artifact.

- [ ] **Step 3: Read back packaged artifacts**

Recalculate SHA256 from the release directory, mount or extract the rootfs, and verify the embedded `dji_rc` contains the new diagnostic field names. Verify the SPI rootfs slice against the standalone rootfs hash.

- [ ] **Step 4: Deploy to V3S and reboot**

Upload and install the new image using the established OTA path, reboot, and reconnect with the newly observed SSH host key.

- [ ] **Step 5: Verify runtime behavior**

Read `/tmp/rc_state.json` after pressing and releasing a 40007 button. Confirm:

- `active_src` is `v3s_adb_rc`.
- `rcmsg_tx_hz` remains approximately 50Hz.
- `adb_40007_edge_tx_count` increases for press and release.
- `adb_40007_edge_tx_us` is normally below 3000us.
- App display follows press and release in order without duplicate replay.

- [ ] **Step 6: Commit release metadata and knowledge backflow**

Commit only tracked release metadata required by the repository, then write and read back the Obsidian knowledge note describing the direct-edge architecture and measured result.
