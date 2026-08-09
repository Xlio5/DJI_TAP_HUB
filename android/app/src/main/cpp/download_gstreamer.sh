#!/bin/bash
# 下载并解压 GStreamer Android SDK 1.28.4 (arm64 静态库 + 头文件)
# 放到 gstreamer_libs/arm64/ 供 CMake 编译使用。
set -e

SDK_URL="https://gstreamer.freedesktop.org/data/pkg/android/1.28.4/gstreamer-1.0-android-universal-1.28.4.tar.xz"
TMP_TAR="$(dirname "$0")/../../../../../../tmp/gstreamer/gstreamer-sdk.tar.xz"
DEST="$(dirname "$0")/../gstreamer_libs/arm64"

if [ -d "$DEST/lib" ] && ls "$DEST"/lib/libgstreamer-1.0.a >/dev/null 2>&1; then
  echo "GStreamer 已就绪: $DEST"
  exit 0
fi

echo "下载 GStreamer Android SDK (~830MB)..."
mkdir -p "$(dirname "$TMP_TAR")"
wget -c -O "$TMP_TAR" "$SDK_URL"

echo "解压..."
rm -rf "$(dirname "$0")/../gstreamer_libs"
mkdir -p "$(dirname "$0")/../gstreamer_libs"
# 在 Linux 文件系统解压避免 Windows 权限问题
WORK=~/gst_sdk_extract
rm -rf "$WORK"
mkdir -p "$WORK"
tar -xf "$TMP_TAR" -C "$WORK"

# 复制 arm64 库 + 头文件
mkdir -p "$DEST"
cp -r "$WORK"/arm64/lib "$DEST/lib"
cp -r "$WORK"/arm64/include "$DEST/include"
# glibconfig.h 在 lib 下
mkdir -p "$DEST/lib/glib-2.0/include"
cp "$WORK"/arm64/lib/glib-2.0/include/glibconfig.h "$DEST/lib/glib-2.0/include/"

echo "GStreamer SDK 就绪: $DEST"
