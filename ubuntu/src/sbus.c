/* SBUS 组帧实现 —— 见 sbus.h。纯 C,可主机单元测试。 */
#include "sbus.h"
#include <string.h>

uint16_t sbus_us_to_val(uint16_t us)
{
    if (us < 1000) us = 1000;
    if (us > 2000) us = 2000;
    /* 线性 1000~2000 -> 172~1811,+500 四舍五入(中位 1500 -> 992) */
    uint32_t span = SBUS_VAL_MAX - SBUS_VAL_MIN;   /* 1639 */
    return (uint16_t)(SBUS_VAL_MIN + ((uint32_t)(us - 1000) * span + 500) / 1000);
}

void sbus_encode(const uint16_t ch_us[16], uint8_t frame[SBUS_FRAME_LEN])
{
    memset(frame, 0, SBUS_FRAME_LEN);
    frame[0] = SBUS_START;
    frame[SBUS_FRAME_LEN - 1] = SBUS_END;

    int bit = 0;
    for (int i = 0; i < 16; i++) {
        uint16_t v = sbus_us_to_val(ch_us[i]) & 0x7FF;   /* 11-bit */
        for (int b = 0; b < 11; b++, bit++)
            if (v & (1u << b))
                frame[1 + bit / 8] |= (uint8_t)(1u << (bit % 8));
    }
    /* frame[23] = flags(ch17/ch18/frame_lost/failsafe) 这里全 0 */
}
