# CMakeLists.txt — TUN_NAT_HUB Ubuntu 守护进程
# 构建: cmake -B build && cmake --build build

cmake_minimum_required(VERSION 3.16)
project(usb_tund VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# 编译选项
add_compile_options(-Wall -Wextra -Wpedantic)
if(CMAKE_BUILD_TYPE STREQUAL "Debug")
    add_compile_options(-g -O0)
else()
    add_compile_options(-O2)
endif()

# 平台检测
if(CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64|arm")
    message(STATUS "目标平台: ARM64")
else()
    message(STATUS "目标平台: ${CMAKE_SYSTEM_PROCESSOR}")
endif()

find_package(Threads REQUIRED)

# 守护进程
add_executable(usb_tund
    src/main.cpp
    src/tun_iface.cpp
)

# ECM/RNDIS 模式不再依赖 frame.h，移除 protocol include
target_link_libraries(usb_tund PRIVATE
    Threads::Threads
)

# 安装
install(TARGETS usb_tund DESTINATION /usr/local/bin)
