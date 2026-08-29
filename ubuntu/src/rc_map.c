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
    "c12", "dir", "lr",
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

/* ── 源配置 (每输入源的输出值, 表驱动, 与 App/固件共享) ── */

const char *rc_cfg_names[CFG_COUNT] = {
    /* 摇杆 ch1-6 */
    "st1_min", "st1_max", "st1_mid", "st1_rev",
    "st2_min", "st2_max", "st2_mid", "st2_rev",
    "st3_min", "st3_max", "st3_mid", "st3_rev",
    "st4_min", "st4_max", "st4_mid", "st4_rev",
    "st5_min", "st5_max", "st5_mid", "st5_rev",
    "st6_min", "st6_max", "st6_mid", "st6_rev",
    /* DIAL */
    "dial_min", "dial_max", "dial_rev",
    /* MODE */
    "mode_s", "mode_n", "mode_f",
    /* 2档开关 (off on lp) */
    "rec_off", "rec_on", "rec_lp",
    "rth_off", "rth_on", "rth_lp",
    "stop_off", "stop_on", "stop_lp",
    "focus_off", "focus_on", "focus_lp",
    "c1_off", "c1_on", "c1_lp",
    "c2_off", "c2_on", "c2_lp",
    "c3_off", "c3_on", "c3_lp",
    "aircraft_off", "aircraft_on", "aircraft_lp",
    "back_off", "back_on", "back_lp",
    "btn_off", "btn_on", "btn_lp",
    "up_off", "up_on", "up_lp",
    "down_off", "down_on", "down_lp",
    "left_off", "left_on", "left_lp",
    "right_off", "right_on", "right_lp",
    /* SHOT */
    "shot_lo", "shot_mid", "shot_hi",
    /* C12 */
    "c12_0", "c12_1", "c12_2", "c12_3",
    /* DIR */
    "dir_0", "dir_1", "dir_2", "dir_3", "dir_4", "dir_5",
    /* LR (L1~R3 互斥自锁 6 档) */
    "lr_0", "lr_1", "lr_2", "lr_3", "lr_4", "lr_5",
};

void rc_cfg_defaults(rc_src_cfg_t *cfg)
{
    static const uint16_t defs[CFG_COUNT] = {
        /* st1-6: min max mid rev = 1000/2000/1500/0 (原行为) */
        1000,2000,1500,0, 1000,2000,1500,0, 1000,2000,1500,0,
        1000,2000,1500,0, 1000,2000,1500,0, 1000,2000,1500,0,
        /* dial (min max rev) */
        1000,2000,0,
        /* mode S/N/F */
        1000,1500,2000,
        /* 14 个 2档开关 off/on/lp (FOCUS 半按=1500, 其余 1000/2000; lp 默认 0=单点) */
        1000,2000,0, 1000,2000,0, 1000,2000,0, 1000,1500,0, 1000,2000,0,
        1000,2000,0, 1000,2000,0, 1000,2000,0, 1000,2000,0, 1000,2000,0,
        1000,2000,0, 1000,2000,0, 1000,2000,0, 1000,2000,0,
        /* shot 松/focus/全按 */
        1000,1500,2000,
        /* c12 无/C1/C2/C1+C2 */
        1000,1333,1667,2000,
        /* dir 无/UP/DN/L/R/BTN */
        1000,1200,1400,1600,1800,2000,
        /* lr L1/L2/L3/R1/R2/R3 (互斥自锁, APM 1000~2000 均分 6 档) */
        1000,1200,1400,1600,1800,2000,
    };
    memcpy(cfg->v, defs, sizeof(defs));
}

static rc_src_cfg_t g_cfg;
static bool g_cfg_init = false;

/* LR 6 档互斥自锁当前档位 (0-5), dji_rc 主循环按下沿推进 (见 update_lr_latch)。 */
int g_lr_pos = 0;

/* 长按确认状态 (dji_rc 计时确认后置 true, 松开置 false)。仅影响独立按键源。 */
static bool g_lp_confirmed[SRC_COUNT] = {};

static void ensure_cfg(void)
{
    if (!g_cfg_init) { rc_cfg_defaults(&g_cfg); g_cfg_init = true; }
}

static const rc_src_cfg_t *rc_cfg_get(void)
{
    ensure_cfg();
    return &g_cfg;
}

void rc_map_set_cfg(const rc_src_cfg_t *cfg)
{
    ensure_cfg();
    if (cfg) g_cfg = *cfg;
    else rc_cfg_defaults(&g_cfg);
}

bool rc_cfg_lp(rc_src_t s)
{
    ensure_cfg();
    switch (s) {
        case SRC_REC:     return g_cfg.v[CFG_REC_LP] != 0;
        case SRC_RTH:     return g_cfg.v[CFG_RTH_LP] != 0;
        case SRC_STOP:    return g_cfg.v[CFG_STOP_LP] != 0;
        case SRC_FOCUS:   return g_cfg.v[CFG_FOCUS_LP] != 0;
        case SRC_C1:      return g_cfg.v[CFG_C1_LP] != 0;
        case SRC_C2:      return g_cfg.v[CFG_C2_LP] != 0;
        case SRC_C3:      return g_cfg.v[CFG_C3_LP] != 0;
        case SRC_AIRCRAFT: return g_cfg.v[CFG_AIRCRAFT_LP] != 0;
        case SRC_BACK:    return g_cfg.v[CFG_BACK_LP] != 0;
        case SRC_BTN:     return g_cfg.v[CFG_BTN_LP] != 0;
        case SRC_UP:      return g_cfg.v[CFG_UP_LP] != 0;
        case SRC_DOWN:    return g_cfg.v[CFG_DOWN_LP] != 0;
        case SRC_LEFT:    return g_cfg.v[CFG_LEFT_LP] != 0;
        case SRC_RIGHT:   return g_cfg.v[CFG_RIGHT_LP] != 0;
        default:          return false;
    }
}

void rc_map_lp_set(rc_src_t s, bool confirmed)
{
    if (s >= 0 && s < SRC_COUNT) g_lp_confirmed[s] = confirmed;
}

bool rc_map_lp_get(rc_src_t s)
{
    return (s >= 0 && s < SRC_COUNT) ? g_lp_confirmed[s] : false;
}

void rc_cfg_sanitize(rc_src_cfg_t *cfg)
{
    for (int i = 0; i < CFG_COUNT; i++) {
        size_t len = strlen(rc_cfg_names[i]);
        if (len >= 4 && strcmp(rc_cfg_names[i] + len - 4, "_rev") == 0) {
            cfg->v[i] = cfg->v[i] ? 1 : 0;          /* 反向标志归一 0/1 */
        } else if (len >= 3 && strcmp(rc_cfg_names[i] + len - 3, "_lp") == 0) {
            cfg->v[i] = cfg->v[i] ? 1 : 0;          /* 长按触发标志归一 0/1 (防被钳到 [800,2200]) */
        } else {
            /* 允许端点微调到 [800,2200], 与 App 通道范围编辑保持一致 */
            if (cfg->v[i] < 800) cfg->v[i] = 800;
            if (cfg->v[i] > 2200) cfg->v[i] = 2200;
        }
    }
    /* 摇杆/dial 的 min/max 排序, 防 min>max 反向映射静默生效 (反向请用 rev) */
    for (int s = 0; s < 6; s++) {
        int mi = CFG_ST1_MIN + s * 4;
        int ma = mi + 1;
        if (cfg->v[mi] > cfg->v[ma]) {
            uint16_t t = cfg->v[mi]; cfg->v[mi] = cfg->v[ma]; cfg->v[ma] = t;
        }
    }
    if (cfg->v[CFG_DIAL_MIN] > cfg->v[CFG_DIAL_MAX]) {
        uint16_t t = cfg->v[CFG_DIAL_MIN];
        cfg->v[CFG_DIAL_MIN] = cfg->v[CFG_DIAL_MAX];
        cfg->v[CFG_DIAL_MAX] = t;
    }
}

/* 单源取值 (us 1000~2000, 应用源配置) */
static uint16_t src_value(const rc_state_t *st, rc_src_t s) {
    const rc_src_cfg_t *c = rc_cfg_get();
    switch (s) {
        case SRC_NONE: return 1000;
        case SRC_CH1: case SRC_CH2: case SRC_CH3:
        case SRC_CH4: case SRC_CH5: case SRC_CH6: {
            int idx = s - SRC_CH1;                       /* 0..5 */
            int16_t v = st->ch[idx];                     /* -660~+660 */
            if (v < -660) v = -660;
            if (v >  660) v =  660;
            const uint16_t *f = &c->v[CFG_ST1_MIN + idx * 4];   /* min max mid rev */
            int16_t mn = f[0], mx = f[1], mid = f[2];
            if (f[3]) v = -v;                            /* 反向 */
            /* 两段线性: 中心为 mid, 端点按 min/max */
            if (v < 0) return (uint16_t)(mid + (mid - mn) * v / 660);
            return (uint16_t)(mid + (mx - mid) * v / 660);
        }
        case SRC_MODE: {
            const uint16_t *f = &c->v[CFG_MODE_S];
            return (st->mode == 'S') ? f[0] : (st->mode == 'N') ? f[1] :
                   (st->mode == 'F') ? f[2] : f[1];
        }
        /* 独立按键源: 配置长按且未确认 (g_lp_confirmed) 时返回 off 值 (短按不触发)。
         * 复合源 (SRC_C12/SHOT/DIR) 读原始字段不受长按影响 — 见下方宏定义。 */
        case SRC_REC: {
            if (rc_cfg_lp(SRC_REC) && !g_lp_confirmed[SRC_REC]) return c->v[CFG_REC_OFF];
            return st->rec ? c->v[CFG_REC_ON] : c->v[CFG_REC_OFF];
        }
        case SRC_RTH: {
            if (rc_cfg_lp(SRC_RTH) && !g_lp_confirmed[SRC_RTH]) return c->v[CFG_RTH_OFF];
            return st->rth ? c->v[CFG_RTH_ON] : c->v[CFG_RTH_OFF];
        }
        case SRC_STOP: {
            if (rc_cfg_lp(SRC_STOP) && !g_lp_confirmed[SRC_STOP]) return c->v[CFG_STOP_OFF];
            return st->stop ? c->v[CFG_STOP_ON] : c->v[CFG_STOP_OFF];
        }
        case SRC_FOCUS: {
            if (rc_cfg_lp(SRC_FOCUS) && !g_lp_confirmed[SRC_FOCUS]) return c->v[CFG_FOCUS_OFF];
            return st->focus ? c->v[CFG_FOCUS_ON] : c->v[CFG_FOCUS_OFF];
        }
        case SRC_C1: {
            if (rc_cfg_lp(SRC_C1) && !g_lp_confirmed[SRC_C1]) return c->v[CFG_C1_OFF];
            return st->c1 ? c->v[CFG_C1_ON] : c->v[CFG_C1_OFF];
        }
        case SRC_C2: {
            if (rc_cfg_lp(SRC_C2) && !g_lp_confirmed[SRC_C2]) return c->v[CFG_C2_OFF];
            return st->c2 ? c->v[CFG_C2_ON] : c->v[CFG_C2_OFF];
        }
        case SRC_C3: {
            if (rc_cfg_lp(SRC_C3) && !g_lp_confirmed[SRC_C3]) return c->v[CFG_C3_OFF];
            return st->c3 ? c->v[CFG_C3_ON] : c->v[CFG_C3_OFF];
        }
        case SRC_DIAL: {
            const uint16_t *f = &c->v[CFG_DIAL_MIN];   /* min max rev */
            int d = st->dial;
            if (d < 0) d = 0;
            if (d > 255) d = 255;
            int16_t mn = f[0], mx = f[1];
            if (f[2]) d = 255 - d;                       /* 反向 */
            return (uint16_t)(mn + (mx - mn) * d / 255);
        }
        case SRC_AIRCRAFT: {
            if (rc_cfg_lp(SRC_AIRCRAFT) && !g_lp_confirmed[SRC_AIRCRAFT]) return c->v[CFG_AIRCRAFT_OFF];
            return st->aircraft ? c->v[CFG_AIRCRAFT_ON] : c->v[CFG_AIRCRAFT_OFF];
        }
        case SRC_BACK: {
            if (rc_cfg_lp(SRC_BACK) && !g_lp_confirmed[SRC_BACK]) return c->v[CFG_BACK_OFF];
            return st->back ? c->v[CFG_BACK_ON] : c->v[CFG_BACK_OFF];
        }
        case SRC_BTN: {
            if (rc_cfg_lp(SRC_BTN) && !g_lp_confirmed[SRC_BTN]) return c->v[CFG_BTN_OFF];
            return st->btn ? c->v[CFG_BTN_ON] : c->v[CFG_BTN_OFF];
        }
        case SRC_UP: {
            if (rc_cfg_lp(SRC_UP) && !g_lp_confirmed[SRC_UP]) return c->v[CFG_UP_OFF];
            return st->up ? c->v[CFG_UP_ON] : c->v[CFG_UP_OFF];
        }
        case SRC_DOWN: {
            if (rc_cfg_lp(SRC_DOWN) && !g_lp_confirmed[SRC_DOWN]) return c->v[CFG_DOWN_OFF];
            return st->down ? c->v[CFG_DOWN_ON] : c->v[CFG_DOWN_OFF];
        }
        case SRC_LEFT: {
            if (rc_cfg_lp(SRC_LEFT) && !g_lp_confirmed[SRC_LEFT]) return c->v[CFG_LEFT_OFF];
            return st->left ? c->v[CFG_LEFT_ON] : c->v[CFG_LEFT_OFF];
        }
        case SRC_RIGHT: {
            if (rc_cfg_lp(SRC_RIGHT) && !g_lp_confirmed[SRC_RIGHT]) return c->v[CFG_RIGHT_OFF];
            return st->right ? c->v[CFG_RIGHT_ON] : c->v[CFG_RIGHT_OFF];
        }
        /* 复合源: 读原始字段, 不受长按过滤影响 (长按仅作用于独立按键源) */
        case SRC_SHOT: {
            const uint16_t *f = &c->v[CFG_SHOT_LO];
            return st->shot ? f[2] : st->focus ? f[1] : f[0];
        }
        case SRC_C12: {
            const uint16_t *f = &c->v[CFG_C12_0];
            int l = ((st->c2 & 1) << 1) | (st->c1 & 1);   /* 0..3 */
            return f[l];
        }
        case SRC_DIR: {
            const uint16_t *f = &c->v[CFG_DIR_0];
            return st->btn ? f[5] : st->up ? f[1] : st->down ? f[2] :
                   st->left ? f[3] : st->right ? f[4] : f[0];
        }
        case SRC_LR: {
            /* 6 档互斥自锁: 档位由 dji_rc update_lr_latch 按 L1~R3 按下沿推进 */
            if (g_lr_pos < 0) g_lr_pos = 0;
            if (g_lr_pos > 5) g_lr_pos = 5;
            return c->v[CFG_LR_0 + g_lr_pos];
        }
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
