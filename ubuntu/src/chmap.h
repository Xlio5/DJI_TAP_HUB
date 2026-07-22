/*
 * 通道映射 —— 把解码/融合后的 RC 状态映射成 16 个通道值(微秒,1000~2000)。
 * 纯 C,无 ESP-IDF 依赖,可主机单元测试。
 *
 * 映射(值 1000~2000µs,中位 1500):
 *   CH1-6  : 解码 CH1-6(模拟, -660~+660 -> 1000~2000)
 *   CH7    : MODE     (S=1000 / N=1500 / F=2000)
 *   CH8    : REC      (2档 1000/2000)
 *   CH9    : RTH      (2档)
 *   CH10   : 快门     (松=1000 / 半按FOCUS=1500 / 全按SHOT=2000)
 *   CH11   : AIRCRAFT (2档)
 *   CH12   : DIAL     (0~255 -> 1000~2000)
 *   CH13   : STOP     (2档)
 *   CH14   : C1+C2 混合 (4档: 无/C1/C2/C1+C2 = 1000/1333/1667/2000)
 *   CH15   : C3       (2档)
 *   CH16   : 方向键+BTN 混合 (6档: 无/UP/DN/L/R/BTN = 1000/1200/1400/1600/1800/2000)
 */
#pragma once

#include <stdint.h>
#include "rc_decode.h"

#define CH_COUNT  16
#define CH_MIN    1000
#define CH_MID    1500
#define CH_MAX    2000

void chmap_build(const rc_state_t *st, uint16_t out[CH_COUNT]);
