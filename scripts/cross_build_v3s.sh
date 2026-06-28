#!/bin/bash
# cross_build_v3s.sh — 一键交叉编译 TUN_NAT_HUB 守护进程到 ARMv7 (V3s)
# 前置: apt install g++-arm-linux-gnueabihf
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$PROJECT_DIR/ubuntu/build_v3s"

echo "=== 交叉编译 TUN_NAT_HUB daemon → ARMv7 (V3s) ==="

mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

cmake .. \
    -DCMAKE_TOOLCHAIN_FILE=../cmake/toolchain-armv7-linux.cmake \
    -DCMAKE_BUILD_TYPE=Release

make -j$(nproc)

echo ""
echo "=== 编译完成 ==="
file usb_tund
ls -lh usb_tund
