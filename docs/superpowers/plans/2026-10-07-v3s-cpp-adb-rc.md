# V3s C++ ADB RC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a small C++ ADB client for V3s so it can read DJI RC joystick `getevent` data over the existing network path without Python or the full Android platform-tools package.

**Architecture:** Build a minimal TCP ADB transport library that supports `CNXN`, optional `AUTH` detection, `OPEN`, `OKAY`, `WRTE`, and `CLSE`. Add a getevent parser that maps DJI event4 ABS axes into the existing `rc_state_t` raw channel semantics (`-660..660`), then expose a standalone `v3s_adb_rc` diagnostic tool for first-stage board validation.

**Tech Stack:** C++17, POSIX sockets, CMake, existing `rc_decode.h` state model.

## Global Constraints

- Do not add Python3 or the full adb/platform-tools package to V3s.
- Keep the first executable small and dependency-free: no OpenSSL, Boost, or libusb.
- Preserve the existing `dji_rc` output path in this stage; do not change live SBUS/CRSF arbitration until the C++ ADB source is proven on board.
- Use Android axis mapping already used by the App: `ABS_RX->ch1`, `ABS_RY->ch2`, `ABS_Y->ch3`, `ABS_X->ch4`, `ABS_RZ->ch5`, `ABS_Z->ch6`.
- Normalize full-range ABS axes to `raw * 660 / 32768` and trigger axes `ABS_Z/ABS_RZ` to `(raw - 127) * 660 / 128`.

---

## File Structure

- Create `ubuntu/src/adb_client.h`: packet types, connection options, and `AdbClient` interface.
- Create `ubuntu/src/adb_client.cpp`: dependency-free TCP ADB packet read/write and shell stream handling.
- Create `ubuntu/src/adb_getevent_rc.h`: event line parser and axis-to-`rc_state_t` conversion interface.
- Create `ubuntu/src/adb_getevent_rc.cpp`: DJI getevent parser and normalization.
- Create `ubuntu/src/v3s_adb_rc.cpp`: CLI tool for V3s validation.
- Create `ubuntu/tests/adb_getevent_rc_test.cpp`: unit tests for packet constants, axis normalization, and parser behavior.
- Modify `ubuntu/CMakeLists.txt`: build the new library, test, and `v3s_adb_rc` executable.

## Task 1: Parser and Packet Unit Tests

**Files:**
- Create: `ubuntu/tests/adb_getevent_rc_test.cpp`
- Create: `ubuntu/src/adb_client.h`
- Create: `ubuntu/src/adb_getevent_rc.h`
- Modify: `ubuntu/CMakeLists.txt`

**Interfaces:**
- Produces: `uint32_t adb_command(const char *cmd4)`, `uint32_t adb_payload_checksum(const uint8_t *data, size_t len)`, `bool parse_getevent_abs_line(const std::string&, GeteventAbsEvent*)`, `bool apply_getevent_axis(const GeteventAbsEvent&, rc_state_t*)`.

- [x] **Step 1: Write failing tests**

Cover ADB packet constants, checksum, event4 filtering, hex signed conversion, DJI axis mapping, and trigger normalization.

- [x] **Step 2: Run test to verify it fails**

Run: `cmake --build ubuntu/build --target adb_getevent_rc_test` before implementation.

- [x] **Step 3: Implement headers and minimal CMake target**

Add declarations and a test target that links the yet-to-be-written implementation.

## Task 2: Minimal ADB Transport

**Files:**
- Create: `ubuntu/src/adb_client.cpp`
- Modify: `ubuntu/src/adb_client.h`
- Test: `ubuntu/tests/adb_getevent_rc_test.cpp`

**Interfaces:**
- Consumes: `adb_command`, `adb_payload_checksum`.
- Produces: `AdbClient::connect()`, `AdbClient::openShell()`, `AdbClient::readShellChunk()`, `AdbClient::close()`.

- [x] **Step 1: Implement packet encode/decode**

Use the standard ADB v1 24-byte header and additive payload checksum.

- [x] **Step 2: Implement TCP connect and CNXN handshake**

Accept direct `CNXN`; if `AUTH` is returned, report a clear error because this no-dependency stage intentionally does not ship RSA signing.

- [x] **Step 3: Implement shell stream**

Send `OPEN shell:<command>\0`, acknowledge `WRTE` packets with `OKAY`, and return shell bytes to the caller.

## Task 3: Getevent RC Reader CLI

**Files:**
- Create: `ubuntu/src/adb_getevent_rc.cpp`
- Create: `ubuntu/src/v3s_adb_rc.cpp`
- Modify: `ubuntu/CMakeLists.txt`

**Interfaces:**
- Consumes: `AdbClient` and parser functions.
- Produces: executable `v3s_adb_rc` with `--host`, `--port`, `--device`, `--seconds`, and `--command`.

- [x] **Step 1: Parse live `getevent -lt` lines**

Maintain one `rc_state_t`, update it on each parsed axis event, and print compact channel lines at a limited rate.

- [x] **Step 2: Add diagnostic shell command mode**

Allow `v3s_adb_rc --command "getprop ro.product.model; id"` for board-side adbd validation without a full adb binary.

## Task 4: Verification and Review

**Files:**
- All new/modified files above.

**Checks:**
- Build host test target.
- Run parser unit test.
- Build `v3s_adb_rc`.
- Run live validation through the current network path when DJI/V3s are reachable.
- Review for blocking issues before commit.

- [x] **Step 1: Run fresh build and tests**
- [x] **Step 2: Run live command-mode validation**
- [x] **Step 3: Run live getevent validation**

  `getevent -lp /dev/input/event4` returned `"DJI embedded joystick"` via V3s C++ ADB.
  The 6-second streaming run opened successfully and exited cleanly with `events=0`; no physical stick movement was present during that window.

- [x] **Step 4: Commit focused changes**
