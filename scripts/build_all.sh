#!/bin/bash
# build_all.sh — 构建 TUN_NAT_HUB 全部组件
# 用法: ./scripts/build_all.sh [debug|release]
# 环境要求:
#   Ubuntu 侧: CMake 3.16+, g++ 9+ (或 aarch64-linux-gnu-g++ 交叉编译链)
#   Android 侧: Android SDK + Gradle Wrapper

set -e

BUILD_TYPE="${1:-debug}"

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
echo "=== TUN_NAT_HUB 构建脚本 ==="
echo "项目根目录: $PROJECT_ROOT"
echo "构建类型: $BUILD_TYPE"
echo ""

# ── Ubuntu 侧构建 ─────────────────────────────────────────────
echo "--- 构建 Ubuntu 服务端 ---"
cd "$PROJECT_ROOT/ubuntu"

if [ ! -f "CMakeLists.txt" ]; then
    echo "[跳过] ubuntu/CMakeLists.txt 不存在，尚未实现"
else
    # 检测是否交叉编译
    if [ -n "$CROSS_COMPILE_ARM64" ] || command -v aarch64-linux-gnu-g++ &>/dev/null; then
        TOOLCHAIN_FILE="$PROJECT_ROOT/ubuntu/cmake/toolchain-arm64.cmake"
        BUILD_DIR="build/arm64"
        if [ -f "$TOOLCHAIN_FILE" ]; then
            cmake -B "$BUILD_DIR" -DCMAKE_TOOLCHAIN_FILE="$TOOLCHAIN_FILE" -DCMAKE_BUILD_TYPE="$BUILD_TYPE"
        else
            echo "交叉编译链可用但无 toolchain 文件，使用原生编译"
            cmake -B "$BUILD_DIR" -DCMAKE_BUILD_TYPE="$BUILD_TYPE"
        fi
    else
        BUILD_DIR="build/native"
        cmake -B "$BUILD_DIR" -DCMAKE_BUILD_TYPE="$BUILD_TYPE"
    fi

    cmake --build "$BUILD_DIR" -- -j$(nproc)
    echo "Ubuntu 构建成功: $BUILD_DIR/usb_tund"
fi

# ── Android 侧构建 ─────────────────────────────────────────────
echo ""
echo "--- 构建 Android APK ---"
cd "$PROJECT_ROOT/android"

if [ ! -f "settings.gradle.kts" ]; then
    echo "[跳过] android/settings.gradle.kts 不存在，尚未实现"
else
    if [ "$BUILD_TYPE" = "release" ]; then
        ./gradlew assembleRelease
        echo "Android 构建成功: app/build/outputs/apk/release/app-release.apk"
    else
        ./gradlew assembleDebug
        echo "Android 构建成功: app/build/outputs/apk/debug/app-debug.apk"
    fi
fi

echo ""
echo "=== 构建完成 ==="
