# V3S ADB Overlap Buttons Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make getevent the exclusive REC/SHOT source in V3S ADB mode and prevent 40007 REC/SHOT changes from emitting direct RCMSG edges.

**Architecture:** Normalize decoded 40007 state at its ownership boundary by clearing fields owned by getevent. Fusion then copies REC/SHOT from getevent instead of OR-ing sources, while all other 40007 fields keep their current behavior.

**Tech Stack:** C++17, CMake, CTest, embedded Linux deployment

---

### Task 1: Reproduce the overlap bug in tests

**Files:**
- Modify: `ubuntu/tests/adb_rc_fusion_test.cpp`

- [ ] Add assertions that fresh getevent release overrides asserted 40007 REC/SHOT.
- [ ] Add assertions that a 40007 normalization helper clears REC/SHOT but preserves STOP.
- [ ] Run `ctest --test-dir ubuntu/build -R adb_rc_fusion_test --output-on-failure` and confirm the new assertions fail for the current OR behavior.

### Task 2: Enforce strict input ownership

**Files:**
- Modify: `ubuntu/src/adb_rc_fusion.h`
- Modify: `ubuntu/src/adb_rc_fusion.cpp`
- Modify: `ubuntu/src/dji_rc.cpp`

- [ ] Add `adb_rc_strip_getevent_owned_buttons(rc_state_t*)` to clear `rec` and `shot` on merged 40007 state.
- [ ] Change fusion so fresh getevent assigns REC/SHOT directly while L1-R3 remain getevent-owned.
- [ ] Normalize merged 40007 state before storing it and before tracking button changes.
- [ ] Rebuild and run the focused test until it passes.
- [ ] Run the complete Ubuntu CTest suite and commit the behavior change.

### Task 3: Build, archive, deploy, and verify

**Files:**
- Modify: `ubuntu/src/web_server.cpp`
- Create: `backup/release_20261011_193525_v1.6.87/manifest.txt`

- [ ] Bump firmware to `v1.6.87` and commit the version change.
- [ ] Build the firmware and create timestamped rootfs/SPI artifacts with SHA256 values and source commit in the manifest.
- [ ] Deploy `dji_rc` and `web_server` to V3S, then read them back and compare SHA256.
- [ ] Verify `/api/version`, `/tmp/rc_state.json`, approximately 50Hz RCMSG, and zero direct-edge send errors.
- [ ] Capture one REC press and confirm only getevent drives the App-visible REC edge.
