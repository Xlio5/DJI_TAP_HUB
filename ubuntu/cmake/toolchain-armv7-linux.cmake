# toolchain-armv7-linux.cmake — V3s / Allwinner sun8i 交叉编译
# 目标: ARMv7-A, glibc (与 V3s 当前 rootfs 一致)
# 用法: cmake -DCMAKE_TOOLCHAIN_FILE=cmake/toolchain-armv7-linux.cmake -B build_v3s

SET(CMAKE_SYSTEM_NAME Linux)
SET(CMAKE_SYSTEM_PROCESSOR armv7)

SET(CMAKE_C_COMPILER   arm-linux-gnueabihf-gcc)
SET(CMAKE_CXX_COMPILER arm-linux-gnueabihf-g++)

SET(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
SET(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
SET(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
SET(CMAKE_FIND_ROOT_PATH_MODE_PACKAGE ONLY)
