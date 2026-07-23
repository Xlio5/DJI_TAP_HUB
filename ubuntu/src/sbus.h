#ifdef __cplusplus
extern "C" {
#endif
/*
 * SBUS 组帧 —— 把 16 个通道(微秒 1000~2000)编成标准 25 字节 SBUS 帧。
 * 纯 C,无 ESP-IDF 依赖,可主机单元测试。
 *
 * 注意: 本项目 SBUS 帧由 dji_rc daemon 通过 ttyS1 @921600 8N1 发送
 *       帧内通道值用标准 SBUS 缩放 172~1811(1000µs->172, 1500->992, 2000->1811)。
 */
#pragma once

#include <stdint.h>

#define SBUS_FRAME_LEN  25
#define SBUS_START      0x0F
#define SBUS_END        0x00
#define SBUS_VAL_MIN    172
#define SBUS_VAL_MID    992
#define SBUS_VAL_MAX    1811

/* 微秒(1000~2000) -> SBUS 11-bit 值(172~1811),越界夹紧,四舍五入使中位=992 */
uint16_t sbus_us_to_val(uint16_t us);

/* 把 16 个微秒通道编成 25 字节 SBUS 帧(flags=0)。 */
void sbus_encode(const uint16_t ch_us[16], uint8_t frame[SBUS_FRAME_LEN]);
#ifdef __cplusplus
}
#endif
