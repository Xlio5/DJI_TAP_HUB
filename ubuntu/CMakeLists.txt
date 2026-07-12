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

target_include_directories(usb_tund PRIVATE
    ${CMAKE_SOURCE_DIR}/../protocol
)

target_link_libraries(usb_tund PRIVATE
    Threads::Threads
)

# 安装
# Web 面板 (C++ 嵌入式 HTTP 服务, 替代 Python3)
add_executable(web_server
    src/web_server.cpp
)

target_link_libraries(web_server PRIVATE
    Threads::Threads
)

install(TARGETS usb_tund web_server DESTINATION /usr/local/bin)
install(FILES ${CMAKE_SOURCE_DIR}/../protocol/frame.h DESTINATION /usr/local/include/tun_nat_hub)
