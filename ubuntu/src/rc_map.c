/* 通道映射实现 —— 见 rc_map.h。纯 C。 */
#include "rc_map.h"
#include <string.h>

static const char *kSrcNames[SRC_COUNT] = {
    "none",
    "ch1", "ch2", "ch3", "ch4", "ch5", "ch6",
    "mode",
    "rec", "rth", "stop", "focus", "shot",
    "c1", "c2", "c3",
    "dial",
    "aircraft", "back",
    "btn", "up", "down", "left", "right",
    "c12", "dir",
};

const char *rc_src_name(rc_src_t s) {
    if (s < 0 || s >= SRC_COUNT) return "none";
    return kSrcNames[s];
}

rc_src_t rc_src_parse(const char *name) {
    for (int i = 0; i < SRC_COUNT; i++)
        if (strcmp(kSrcNames[i], name) == 0) return (rc_src_t)i;
    return SRC_NONE;
}

const char *rc_preset_name(rc_map_preset_t p) {
    switch (p) {
        case MAP_DEFAULT: return "default";
        case MAP_AETR:    return "aetr";
        case MAP_TAER:    return "taer";
        default:          return "custom";
    }
}

rc_map_preset_t rc_preset_parse(const char *name) {
    if (!name) return MAP_CUSTOM;
    if (strcmp(name, "aetr") == 0) return MAP_AETR;
    if (strcmp(name, "taer") == 0) return MAP_TAER;
    if (strcmp(name, "default") == 0) return MAP_DEFAULT;
    return MAP_CUSTOM;
}

void rc_map_default(uint8_t map[CH_COUNT]) {
    /* CH1-6 摇杆; CH7 mode; CH8 rec; CH9 rth; CH10 快门; CH11 aircraft;
     * CH12 dial; CH13 stop; CH14 c12; CH15 c3; CH16 dir */
    const uint8_t d[CH_COUNT] = {
        SRC_CH1, SRC_CH2, SRC_CH3, SRC_CH4, SRC_CH5, SRC_CH6,
        SRC_MODE, SRC_REC, SRC_RTH, SRC_FOCUS, SRC_AIRCRAFT,
        SRC_DIAL, SRC_STOP, SRC_C12, SRC_C3, SRC_DIR,
    };
    memcpy(map, d, CH_COUNT);
}

void rc_map_apply_preset(rc_map_preset_t p, uint8_t map[CH_COUNT]) {
    uint8_t d[CH_COUNT];
    rc_map_default(d);
    if (p == MAP_DEFAULT) { memcpy(map, d, CH_COUNT); return; }

    /* AETR/TAER 重排 CH1-4 (只改前 4 项 source) */
    memcpy(map, d, CH_COUNT);
    /* 默认 CH1..CH4 已是 ch1,ch2,ch3,ch4。
     * AETR: 输出 CH1=ch1(A) CH2=ch2(E) CH3=ch3(T) CH4=ch4(R) — 同默认物理序
     * 但不同飞控约定不同, 这里 AETR 保持 ch1..ch4, TAER 重排为 ch3,ch1,ch2,ch4
     * (即 油门到 CH1, 副翼到 CH2, 升降到 CH3) */
    if (p == MAP_TAER) {
        map[0] = SRC_CH3;   /* CH1 = 油门(ch3) */
        map[1] = SRC_CH1;   /* CH2 = 副翼(ch1) */
        map[2] = SRC_CH2;   /* CH3 = 升降(ch2) */
        map[3] = SRC_CH4;   /* CH4 = 方向(ch4) */
    }
}

/* 单源取值 (us 1000~2000) */
static uint16_t src_value(const rc_state_t *st, rc_src_t s) {
    switch (s) {
        case SRC_NONE: return 1000;
        case SRC_CH1: case SRC_CH2: case SRC_CH3:
        case SRC_CH4: case SRC_CH5: case SRC_CH6: {
            int16_t v = st->ch[s - SRC_CH1];   /* -660~+660 */
            if (v < -660) v = -660;
            if (v >  660) v =  660;
            return (uint16_t)(1500 + (int)v * 500 / 660);
        }
        case SRC_MODE:
            return (st->mode == 'S') ? 1000 : (st->mode == 'N') ? 1500 :
                   (st->mode == 'F') ? 2000 : 1500;
        case SRC_REC:   return st->rec ? 2000 : 1000;
        case SRC_RTH:   return st->rth ? 2000 : 1000;
        case SRC_STOP:  return st->stop ? 2000 : 1000;
        case SRC_FOCUS: return st->focus ? 1500 : 1000;   /* 半按 */
        case SRC_SHOT:  return st->shot ? 2000 : (st->focus ? 1500 : 1000);
        case SRC_C1:    return st->c1 ? 2000 : 1000;
        case SRC_C2:    return st->c2 ? 2000 : 1000;
        case SRC_C3:    return st->c3 ? 2000 : 1000;
        case SRC_DIAL:  return (uint16_t)(1000 + (int)st->dial * 1000 / 255);
        case SRC_AIRCRAFT: return st->aircraft ? 2000 : 1000;
        case SRC_BACK:  return st->back ? 2000 : 1000;
        case SRC_BTN:   return st->btn ? 2000 : 1000;
        case SRC_UP:    return st->up ? 2000 : 1000;
        case SRC_DOWN:  return st->down ? 2000 : 1000;
        case SRC_LEFT:  return st->left ? 2000 : 1000;
        case SRC_RIGHT: return st->right ? 2000 : 1000;
        case SRC_C12: {
            static const uint16_t lvl[4] = {1000, 1333, 1667, 2000};
            int l = ((st->c2 & 1) << 1) | (st->c1 & 1);
            return lvl[l];
        }
        case SRC_DIR:
            return st->btn ? 2000 : st->up ? 1200 : st->down ? 1400 :
                   st->left ? 1600 : st->right ? 1800 : 1000;
        default: return 1000;
    }
}

void rc_map_build(const rc_state_t *st, const uint8_t map[CH_COUNT],
                  uint16_t out[CH_COUNT]) {
    uint8_t d[CH_COUNT];
    if (map == NULL) { rc_map_default(d); map = d; }
    for (int i = 0; i < CH_COUNT; i++)
        out[i] = src_value(st, (rc_src_t)map[i]);
}
