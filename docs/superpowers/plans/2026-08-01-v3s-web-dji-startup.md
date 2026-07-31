# V3s Web And DJI Startup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build firmware that boots the current C++ web panel and persistent DJI RC daemon with 5-second UART0 debug output.

**Architecture:** Keep V3s services as BusyBox init-managed processes from `/usr/local/bin`. The full rebuild script compiles current host sources with the Buildroot toolchain and installs binaries into the Buildroot target before rootfs packaging.

**Tech Stack:** C++17, C modules, Buildroot 2024.02, BusyBox init, SquashFS, Allwinner V3s.

## Global Constraints

- Use `ubuntu/src/web_server.cpp` as the V3s web source.
- Do not start `ubuntu/web_panel.py` on V3s firmware.
- Start `dji_rc` at boot with UART0 debug on `/dev/ttyS0 @115200`.
- Output DJI latest channel debug every 5 seconds.
- Output SBUS on `/dev/ttyS2 @115200`.
- Verify builds before claiming completion.

---

### Task 1: DJI Runtime Behavior

**Files:**
- Modify: `ubuntu/src/dji_rc.cpp`
- Modify: `ubuntu/scripts/S99tun_nat_hub`

**Interfaces:**
- Consumes: existing `--debug-uart0`, `--debug-uart0-baud`, `--sbus-out`, and `--sbus-baud` options.
- Produces: boot command that runs `/usr/local/bin/dji_rc --debug-uart0 --debug-uart0-baud 115200 --sbus-out /dev/ttyS2 --sbus-baud 115200`.

- [ ] Change debug interval from 1 second to 5 seconds.
- [ ] Update `S99tun_nat_hub` to start `dji_rc` with the persistent debug and SBUS options.
- [ ] Compile `dji_rc` with the Buildroot toolchain.

### Task 2: Full Rootfs Build

**Files:**
- Modify: `scripts/rebuild_full_clean.sh`

**Interfaces:**
- Consumes: Buildroot toolchain from `/home/xlong/v3s/buildroot-2024.02/output/host/bin`.
- Produces: `output/target/usr/local/bin/web_server`, `output/target/usr/local/bin/dji_rc`, and `backup/rootfs.squashfs`.

- [ ] Explicitly compile `web_server` from `ubuntu/src/web_server.cpp`.
- [ ] Explicitly compile `dji_rc` from `ubuntu/src/dji_rc.cpp` plus `duml.c`, `rc_decode.c`, `chmap.c`, and `sbus.c`.
- [ ] Install both binaries into the Buildroot target and overlay before rootfs packaging.
- [ ] Verify target paths exist before building SquashFS.

### Task 3: Verification And Flash Readback

**Files:**
- Read: `backup/rootfs.squashfs`
- Read: `backup/spi_image.bin`

**Interfaces:**
- Consumes: FEL mode and `sunxi-fel`.
- Produces: readback hash comparison for written SPI regions.

- [ ] Run full rebuild.
- [ ] Verify `web_server`, `dji_rc`, and `S99tun_nat_hub` exist in the rootfs staging area.
- [ ] Flash only after the board is in FEL mode.
- [ ] Read back flashed contents and compare hashes.
