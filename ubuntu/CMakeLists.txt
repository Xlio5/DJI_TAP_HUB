# CMakeLists.txt — TUN_NAT_HUB Ubuntu 守护进程
# 构建: cmake -B build && cmake --build build

cmake_minimum_required(VERSION 3.16)
project(usb_tund VERSION 1.0.0 LANGUAGES C CXX)

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
include(CTest)

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
# apiRcOutput 依赖 rc_map (通道映射名 + 源解析), 必须链接
add_executable(web_server
    src/web_server.cpp
    src/rc_map.c
    src/rc_input_mode.cpp
)

target_link_libraries(web_server PRIVATE
    Threads::Threads
)

add_executable(rtsp_nat_helper_test
    tests/rtsp_nat_helper_test.cpp
)

target_include_directories(rtsp_nat_helper_test PRIVATE
    ${CMAKE_SOURCE_DIR}/src
)

add_executable(rc_source_select_test
    tests/rc_source_select_test.cpp
    src/rc_source_select.cpp
)

add_executable(rc_input_mode_test
    tests/rc_input_mode_test.cpp
    src/rc_input_mode.cpp
)

target_include_directories(rc_input_mode_test PRIVATE
    ${CMAKE_SOURCE_DIR}/src
)

add_test(NAME rc_input_mode_test COMMAND rc_input_mode_test)

target_include_directories(rc_source_select_test PRIVATE
    ${CMAKE_SOURCE_DIR}/src
)

add_executable(adb_getevent_rc_test
    tests/adb_getevent_rc_test.cpp
    src/adb_client.cpp
    src/adb_getevent_rc.cpp
)

target_include_directories(adb_getevent_rc_test PRIVATE
    ${CMAKE_SOURCE_DIR}/src
)

add_test(NAME adb_getevent_rc_test COMMAND adb_getevent_rc_test)

add_executable(adb_multiplex_test
    tests/adb_multiplex_test.cpp
    src/adb_client.cpp
)

target_include_directories(adb_multiplex_test PRIVATE
    ${CMAKE_SOURCE_DIR}/src
)

add_test(NAME adb_multiplex_test COMMAND adb_multiplex_test)

add_executable(adb_rc_fusion_test
    tests/adb_rc_fusion_test.cpp
    src/adb_rc_fusion.cpp
)

target_include_directories(adb_rc_fusion_test PRIVATE
    ${CMAKE_SOURCE_DIR}/src
)

add_test(NAME adb_rc_fusion_test COMMAND adb_rc_fusion_test)

add_executable(rc_event_gate_test
    tests/rc_event_gate_test.cpp
    src/rc_event_gate.cpp
)

target_include_directories(rc_event_gate_test PRIVATE
    ${CMAKE_SOURCE_DIR}/src
)

target_link_libraries(rc_event_gate_test PRIVATE
    Threads::Threads
)

add_test(NAME rc_event_gate_test COMMAND rc_event_gate_test)

install(TARGETS usb_tund web_server DESTINATION /usr/local/bin)

# DJI RC 双路串口解码守护进程
# 注意: dji_rc.cpp 使用 crsf.c (CRSF 编解码/回传) 和 rc_map.c (通道映射), 必须链接
add_executable(dji_rc
    src/dji_rc.cpp
    src/rc_event_gate.cpp
    src/rc_input_mode.cpp
    src/adb_client.cpp
    src/adb_getevent_rc.cpp
    src/adb_rc_fusion.cpp
    src/rc_source_select.cpp
    src/duml.c
    src/rc_decode.c
    src/chmap.c
    src/sbus.c
    src/crsf.c
    src/rc_map.c
)

add_executable(v3s_adb_rc
    src/v3s_adb_rc.cpp
    src/adb_client.cpp
    src/adb_getevent_rc.cpp
)

target_include_directories(v3s_adb_rc PRIVATE
    ${CMAKE_SOURCE_DIR}/src
)

add_executable(aux_uart_test
    src/aux_uart_test.cpp
)

target_link_libraries(dji_rc PRIVATE
    Threads::Threads
)

install(TARGETS dji_rc aux_uart_test DESTINATION /usr/local/bin)
install(TARGETS v3s_adb_rc DESTINATION /usr/local/bin)
install(FILES ${CMAKE_SOURCE_DIR}/../protocol/frame.h DESTINATION /usr/local/include/tun_nat_hub)
