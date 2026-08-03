/*
 * 通道映射 —— 把 rc_state_t 按可配置映射表转成 16 个输出通道(us 1000~2000)。
 * 纯 C, 参考 EdgeTX 混控: 每条输出通道指定一个输入源(source)。
 *
 * source 定义:
 *   CH1..CH6  : 解码摇杆(直接用 us 值)
 *   MODE      : 3档 S/N/F -> 1000/1500/2000
 *   REC/RTH/STOP/FOCUS/SHOT/C1/C2/C3/AIRCRAFT/BACK/BTN/UP/DOWN/LEFT/RIGHT:
 *               2档开关 -> 1000/2000
 *   DIAL      : 0~255 -> 1000~2000 (线性)
 *   C12       : C1+C2 混合 4档 (无/C1/C2/C1+C2 = 1000/1333/1667/2000)
 *   DIR       : 方向键+BTN 混合 6档 (BTN>UP>DN>L>R>无)
 *
 * 预设 (map 数组头 4 项对应 AETR/TAER 重排):
 *   MAP_DEFAULT : CH1=CH1 CH2=CH2 CH3=CH3 CH4=CH4 (默认物理顺序)
 *   MAP_AETR    : CH1=A CH2=E CH3=T CH4=R  (即 ch0,ch1,ch2,ch3)
 *   MAP_TAER    : CH1=T CH2=A CH3=E CH4=R
 *   其余 CH5-16 两种预设相同(接默认)。
 * 自定义: map 数组每项为任意 source。
 */
#pragma once

#include <stdint.h>
#include <stdbool.h>
#include "rc_decode.h"

#define CH_COUNT 16

/* source 枚举 (值同时用作配置字符串索引) */
typedef enum {
    SRC_NONE = 0,
    SRC_CH1, SRC_CH2, SRC_CH3, SRC_CH4, SRC_CH5, SRC_CH6,
    SRC_MODE,
    SRC_REC, SRC_RTH, SRC_STOP, SRC_FOCUS, SRC_SHOT,
    SRC_C1, SRC_C2, SRC_C3,
    SRC_DIAL,
    SRC_AIRCRAFT, SRC_BACK,
    SRC_BTN, SRC_UP, SRC_DOWN, SRC_LEFT, SRC_RIGHT,
    SRC_C12,        /* C1+C2 混合 4档 */
    SRC_DIR,        /* 方向键+BTN 混合 6档 */
    SRC_COUNT
} rc_src_t;

/* 预设 */
typedef enum {
    MAP_DEFAULT = 0,
    MAP_AETR,
    MAP_TAER,
    MAP_CUSTOM
} rc_map_preset_t;

#define RC_SRC_NAME_MAX  12

/* source 名称 <-> 枚举 */
const char *rc_src_name(rc_src_t s);
rc_src_t    rc_src_parse(const char *name);

/* 预设名 */
const char *rc_preset_name(rc_map_preset_t p);
rc_map_preset_t rc_preset_parse(const char *name);

/* 按映射表生成 16 通道 us 值。map 为 NULL 时用默认映射。 */
void rc_map_build(const rc_state_t *st, const uint8_t map[CH_COUNT],
                  uint16_t out[CH_COUNT]);

/* 生成默认映射数组 (MAP_DEFAULT) */
void rc_map_default(uint8_t map[CH_COUNT]);

/* 预设 -> map 数组。预设只重排 CH1-4, 其余同默认。 */
void rc_map_apply_preset(rc_map_preset_t p, uint8_t map[CH_COUNT]);
