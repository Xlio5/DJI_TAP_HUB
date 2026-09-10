/*
 * 通道映射 —— 把 rc_state_t 按可配置映射表转成 16 个输出通道(us 1000~2000)。
 * 纯 C, 参考 EdgeTX 混控: 每条输出通道指定一个输入源(source)。
 *
 * source 定义:
 *   CH1..CH6  : 解码摇杆(直接用 us 值)
 *   MODE      : 3档 S/N/F -> 1000/1500/2000
 *   REC/RTH/STOP/C1/C2/C3/AIRCRAFT/BACK/BTN/UP/DOWN/LEFT/RIGHT:
 *               2档开关 -> 1000/2000
 *   FOCUS/SHOT : 同一个两段式快门键，松开/半按/全按 -> 1000/1500/2000
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

#ifdef __cplusplus
extern "C" {
#endif

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
    SRC_LR,         /* L1~R3 互斥单选 6档 (自锁) */
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

/* ── 源配置 (每输入源的输出值, 参考 EdgeTX 混控) ──
 * 每个输入源可自定义其映射到输出通道时的数值:
 *   摇杆/Dial: min/max/mid/rev (两段线性缩放)
 *   MODE/FOCUS/SHOT : 三档值 (S/N/F 或 快门松/focus半按/shot全按)
 *   2档开关   : off/on 触发值
 *   C12 4档 / DIR 6档: 每档位值
 * 表驱动存 85 个 uint16 (rc_cfg_names 给出 JSON key), web_server/dji_rc/App 共享。 */

#define RC_CFG_NUM 91   /* 源配置参数总数 */

/* 源配置参数索引 (顺序与 rc_cfg_names/默认值表一致, 勿乱序) */
enum {
    /* 摇杆 ch1-6 (每源 4 项: min max mid rev) */
    CFG_ST1_MIN = 0, CFG_ST1_MAX, CFG_ST1_MID, CFG_ST1_REV,
    CFG_ST2_MIN, CFG_ST2_MAX, CFG_ST2_MID, CFG_ST2_REV,
    CFG_ST3_MIN, CFG_ST3_MAX, CFG_ST3_MID, CFG_ST3_REV,
    CFG_ST4_MIN, CFG_ST4_MAX, CFG_ST4_MID, CFG_ST4_REV,
    CFG_ST5_MIN, CFG_ST5_MAX, CFG_ST5_MID, CFG_ST5_REV,
    CFG_ST6_MIN, CFG_ST6_MAX, CFG_ST6_MID, CFG_ST6_REV,
    /* DIAL 旋钮 (线性 min→max, 无中位) */
    CFG_DIAL_MIN, CFG_DIAL_MAX, CFG_DIAL_REV,
    /* MODE 三档 S/N/F */
    CFG_MODE_S, CFG_MODE_N, CFG_MODE_F,
    /* 2档开关 (每源 3 项: off on lp, lp=长按触发标志 0/1) */
    CFG_REC_OFF, CFG_REC_ON, CFG_REC_LP,
    CFG_RTH_OFF, CFG_RTH_ON, CFG_RTH_LP,
    CFG_STOP_OFF, CFG_STOP_ON, CFG_STOP_LP,
    CFG_FOCUS_OFF, CFG_FOCUS_ON, CFG_FOCUS_LP,
    CFG_C1_OFF, CFG_C1_ON, CFG_C1_LP,
    CFG_C2_OFF, CFG_C2_ON, CFG_C2_LP,
    CFG_C3_OFF, CFG_C3_ON, CFG_C3_LP,
    CFG_AIRCRAFT_OFF, CFG_AIRCRAFT_ON, CFG_AIRCRAFT_LP,
    CFG_BACK_OFF, CFG_BACK_ON, CFG_BACK_LP,
    CFG_BTN_OFF, CFG_BTN_ON, CFG_BTN_LP,
    CFG_UP_OFF, CFG_UP_ON, CFG_UP_LP,
    CFG_DOWN_OFF, CFG_DOWN_ON, CFG_DOWN_LP,
    CFG_LEFT_OFF, CFG_LEFT_ON, CFG_LEFT_LP,
    CFG_RIGHT_OFF, CFG_RIGHT_ON, CFG_RIGHT_LP,
    /* SHOT 三档 (松/focus 半按/全按) */
    CFG_SHOT_LO, CFG_SHOT_MID, CFG_SHOT_HI,
    /* C12 四档 (无/C1/C2/C1+C2) */
    CFG_C12_0, CFG_C12_1, CFG_C12_2, CFG_C12_3,
    /* DIR 六档 (无/UP/DN/L/R/BTN) */
    CFG_DIR_0, CFG_DIR_1, CFG_DIR_2, CFG_DIR_3, CFG_DIR_4, CFG_DIR_5,
    /* LR 六档 (L1/L2/L3/R1/R2/R3 互斥自锁) */
    CFG_LR_0, CFG_LR_1, CFG_LR_2, CFG_LR_3, CFG_LR_4, CFG_LR_5,
    CFG_COUNT   /* = RC_CFG_NUM = 91 */
};

typedef struct {
    uint16_t v[RC_CFG_NUM];
} rc_src_cfg_t;

/* 参数名表 (JSON key, 顺序与 CFG_* 索引一致) */
extern const char *rc_cfg_names[CFG_COUNT];

/* 填默认值 (默认 = 原硬编码行为) */
void rc_cfg_defaults(rc_src_cfg_t *cfg);

/* 清理配置值: _rev 归一 0/1, 其余钳位 [800,2200], 防非法脉宽 */
void rc_cfg_sanitize(rc_src_cfg_t *cfg);

/* 设置源配置; cfg==NULL 恢复默认。rc_map_build 读此配置。 */
void rc_map_set_cfg(const rc_src_cfg_t *cfg);

/* 该源是否配置长按触发 (0=单点, 1=长按≥500ms 才触发)。dji_rc 调用方须持 g_mtx。 */
bool rc_cfg_lp(rc_src_t s);

/* LR 6 档互斥自锁当前档位 (0-5), dji_rc 主循环按 L1~R3 按下沿推进。 */
extern int g_lr_pos;

/* 长按确认状态: dji_rc 计时确认后置 true (src_value 对独立按键源检查),
 * 仅影响独立按键源, 复合源 (C12/SHOT/DIR) 读原始字段不受影响。 */
void rc_map_lp_set(rc_src_t s, bool confirmed);
bool rc_map_lp_get(rc_src_t s);

#ifdef __cplusplus
}
#endif
