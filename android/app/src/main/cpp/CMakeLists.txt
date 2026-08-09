cmake_minimum_required(VERSION 3.22)
project(gstqgcplayer C CXX)

# GStreamer Android SDK 路径 (已解压到项目内)
set(GSTREAMER_ROOT ${CMAKE_SOURCE_DIR}/../gstreamer_libs)
if(NOT EXISTS "${GSTREAMER_ROOT}/arm64")
    message(FATAL_ERROR "GStreamer SDK not found at ${GSTREAMER_ROOT}/arm64. Download and extract first.")
endif()

set(ANDROID_ABI_NAMESPACE "arm64")

# GStreamer 静态库目录
set(GST_LIB_DIR "${GSTREAMER_ROOT}/${ANDROID_ABI_NAMESPACE}/lib")
set(GST_INCLUDE_DIR "${GSTREAMER_ROOT}/${ANDROID_ABI_NAMESPACE}/include")
set(GST_PLUGINS_DIR "${GSTREAMER_ROOT}/${ANDROID_ABI_NAMESPACE}/lib/gstreamer-1.0")

# 包含 GStreamer 头
include_directories(
    ${GST_INCLUDE_DIR}
    ${GST_INCLUDE_DIR}/gstreamer-1.0
    ${GST_INCLUDE_DIR}/glib-2.0
    ${GST_INCLUDE_DIR}/libxml2
    ${GST_LIB_DIR}/glib-2.0/include
)

# 插件库 (仅需要的) — whole-archive 防止插件内部 element 被裁剪
# rtspsrc, decodebin3, videoconvert, videoscale, appsink, androidmedia
set(GST_PLUGIN_LIBS
    -Wl,--whole-archive
    ${GST_PLUGINS_DIR}/libgstrtsp.a
    ${GST_PLUGINS_DIR}/libgstrtp.a
    ${GST_PLUGINS_DIR}/libgstrtpmanager.a
    ${GST_PLUGINS_DIR}/libgstplayback.a
    ${GST_PLUGINS_DIR}/libgstcoreelements.a
    ${GST_PLUGINS_DIR}/libgstapp.a
    ${GST_PLUGINS_DIR}/libgstvideoconvertscale.a
    ${GST_PLUGINS_DIR}/libgstvideoparsersbad.a
    ${GST_PLUGINS_DIR}/libgstandroidmedia.a
    ${GST_PLUGINS_DIR}/libgsttypefindfunctions.a
    ${GST_PLUGINS_DIR}/libgsttcp.a
    ${GST_PLUGINS_DIR}/libgstudp.a
    ${GST_PLUGINS_DIR}/libgstsdpelem.a
    ${GST_PLUGINS_DIR}/libgstopenh264.a
    ${GST_PLUGINS_DIR}/libgstopengl.a
    -Wl,--no-whole-archive
)

# 核心 GStreamer 静态库
set(GST_CORE_LIBS
    ${GST_LIB_DIR}/libgstreamer-1.0.a
    ${GST_LIB_DIR}/libgstbase-1.0.a
    ${GST_LIB_DIR}/libgstcontroller-1.0.a
    ${GST_LIB_DIR}/libgstnet-1.0.a
    ${GST_LIB_DIR}/libgstcheck-1.0.a
    ${GST_LIB_DIR}/libgstrtsp-1.0.a
    ${GST_LIB_DIR}/libgstrtp-1.0.a
    ${GST_LIB_DIR}/libgstsdp-1.0.a
    ${GST_LIB_DIR}/libgstvideo-1.0.a
    ${GST_LIB_DIR}/libgstapp-1.0.a
    ${GST_LIB_DIR}/libgstaudio-1.0.a
    ${GST_LIB_DIR}/libgstpbutils-1.0.a
    ${GST_LIB_DIR}/libgsttag-1.0.a
    ${GST_LIB_DIR}/libgstfft-1.0.a
    ${GST_LIB_DIR}/libgstallocators-1.0.a
    ${GST_LIB_DIR}/libgsturidownloader-1.0.a
    ${GST_LIB_DIR}/libgstcodecparsers-1.0.a
    ${GST_LIB_DIR}/libgstphotography-1.0.a
)

# (软解暂用 androidmedia 硬解, openh264/libav 后需 C++ 运行时, 暂缓)

# GLib
set(GLIB_LIBS
    ${GST_LIB_DIR}/libglib-2.0.a
    ${GST_LIB_DIR}/libgobject-2.0.a
    ${GST_LIB_DIR}/libgmodule-2.0.a
    ${GST_LIB_DIR}/libgthread-2.0.a
    ${GST_LIB_DIR}/libgio-2.0.a
    ${GST_LIB_DIR}/libgstgl-1.0.a
)

# 其他依赖
set(DEPS_LIBS
    ${GST_LIB_DIR}/libz.a
    ${GST_LIB_DIR}/libxml2.a
    ${GST_LIB_DIR}/libffi.a
    ${GST_LIB_DIR}/libiconv.a
    ${GST_LIB_DIR}/libintl.a
    ${GST_LIB_DIR}/libbz2.a
    ${GST_LIB_DIR}/libpcre2-8.a
    ${GST_LIB_DIR}/liborc-0.4.a
    ${GST_LIB_DIR}/libgraphene-1.0.a
    ${GST_LIB_DIR}/libjpeg.a
    ${GST_LIB_DIR}/libpng16.a
)

# OpenH264 (H264 软解, C++ 库)
set(OPENH264_LIBS
    ${GST_LIB_DIR}/libopenh264.a
)

add_library(gstqgcplayer SHARED gstqgc_player.c)

# GStreamer 静态库有循环依赖，必须用 --start-group/--end-group 包裹
target_link_libraries(gstqgcplayer
    -Wl,--start-group
    ${GST_PLUGIN_LIBS}
    ${GST_CORE_LIBS}
    ${GLIB_LIBS}
    ${DEPS_LIBS}
    ${OPENH264_LIBS}
    -Wl,--end-group
    log
    android
    GLESv2
    EGL
)

# openh264 是 C++ 库: 加一个空 .cpp 源让 CMake 启用 C++ 链接器 + C++ 运行时
target_sources(gstqgcplayer PRIVATE gstqgc_plugin_link.cpp)
target_compile_options(gstqgcplayer PRIVATE -DANDROID -fPIC -Wno-unused-parameter -fexceptions -frtti)
