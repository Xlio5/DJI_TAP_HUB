/* DJI 摇杆/按键解码层实现 —— 见 rc_decode.h。纯 C,可主机单元测试。 */
#include "rc_decode.h"

#include <stdio.h>
#include <string.h>

const char *rc_type_name(rc_type_t t)
{
    switch (t) {
        case RC_AE:      return "RC/0xAE";
        case RC_SPECIAL: return "SPECIAL/0x02";
        case RC_APP_FUSED: return "APP/RCM1";
        default:         return "NONE";
    }
}

/* ── RC/0xAE (RC Plus 2, 17B payload) ──────────────────────────────────
 * byte0 : FOCUS(7) SHOT(6) RTH(5) STOP(4)
 * byte1 : UP(7) DOWN(6) LEFT(5) RIGHT(4) CENTER(3) AIRCRAFT(2) BACK(1) REC(0)
 * byte2 : C3(4) C2(3) C1(2) MODE(1..0)
 * byte3 : reserved
 * byte4 : DIAL
 * byte5..16 : 6 × uint16 LE ADC(0..2047,中位1024)
 */
bool decode_rc_ae(const uint8_t *pl, int pl_len, rc_state_t *st)
{
    if (pl == NULL || pl_len < 17) return false;

    memset(st, 0, sizeof(*st));
    st->type = RC_AE;

    const uint8_t b0 = pl[0], b1 = pl[1], b2 = pl[2], b4 = pl[4];

    for (int i = 0; i < 6; i++) {
        uint16_t raw = (uint16_t)(pl[5 + i * 2] | (pl[6 + i * 2] << 8));
        st->ch[i] = (int16_t)((int)raw - 1024);
    }
    /* 实机确认: DJI RC Plus 2 (RC/0xAE) 的 ADC 通道顺序与物理摇杆错位,
     * CH5(ch[4])/CH6(ch[5]) 需对调才与物理控件一致 (实测验证)。 */
    {
        int16_t t = st->ch[4]; st->ch[4] = st->ch[5]; st->ch[5] = t;
    }

    const int m = b2 & 0x3;
    /* mode 映射按实机纠正: m=1->N, m=2->F(与 P20/SPECIAL 一致) */
    st->mode = (m == 0) ? 'S' : (m == 1) ? 'N' : (m == 2) ? 'F' : '?';

    st->btn      = (b1 >> 3) & 1;                  /* CENTER */
    st->stop     = (b0 >> 4) & 1;
    st->focus    = (b0 >> 7) & 1;
    st->shot     = (b0 >> 6) & 1;
    st->rec      = b1 & 1;
    st->rth      = (b0 >> 5) & 1;
    st->up       = (b1 >> 7) & 1;
    st->down     = (b1 >> 6) & 1;
    st->left     = (b1 >> 5) & 1;
    st->right    = (b1 >> 4) & 1;
    st->aircraft = (b1 >> 2) & 1;
    st->back     = (b1 >> 1) & 1;
    st->c1       = (b2 >> 2) & 1;
    st->c2       = (b2 >> 3) & 1;
    st->c3       = (b2 >> 4) & 1;
    st->dial     = b4;
    return true;
}

/* ── SPECIAL/0x02 (旧版遥控器, 13B payload) ─────────────────────────────
 * 6 个 11-bit 通道位域,起始 bit: 8,19,30,41,52,63
 * 按键在 pl[10..12]。
 */
static int16_t special_ch(const uint8_t *pl, int start)
{
    int bo = start / 8, bi = start % 8;
    uint32_t v = 0;
    for (int j = 0; j < 4 && bo + j < 13; j++)
        v |= (uint32_t)pl[bo + j] << (j * 8);
    uint16_t r = (uint16_t)((v >> bi) & 0x3FF);       /* 低 10 位 */
    int mb = (start + 10) / 8, mi = (start + 10) % 8;
    if (mb < 13) r |= (uint16_t)(((pl[mb] >> mi) & 1) << 10);  /* 第 11 位 */
    return (int16_t)((int)r - 1024);
}

bool decode_special_02(const uint8_t *pl, int pl_len, rc_state_t *st)
{
    if (pl == NULL || pl_len < 13) return false;

    static const int starts[6] = { 8, 19, 30, 41, 52, 63 };
    memset(st, 0, sizeof(*st));
    st->type = RC_SPECIAL;

    for (int i = 0; i < 6; i++)
        st->ch[i] = special_ch(pl, starts[i]);

    const int m = (pl[12] >> 2) & 0x3;
    st->mode  = (m == 0) ? 'S' : (m == 1) ? 'N' : (m == 2) ? 'F' : '?';
    st->btn   = 0;   /* SPECIAL 的 pl[11]&1 实为 C3,中心键只从 RC/0xAE 取,这里不置 btn */
    st->stop  = (pl[12] >> 4) & 1;
    st->focus = (pl[10] >> 6) & 1;
    st->shot  = (pl[12] >> 0) & 1;
    st->rec   = (pl[12] >> 5) & 1;
    return true;
}

int rc_state_to_kv(const rc_state_t *st, char *out, size_t n)
{
    int w = snprintf(out, n,
        "CH1=%+d CH2=%+d CH3=%+d CH4=%+d CH5=%+d CH6=%+d "
        "MODE=%c BTN=%d STOP=%d FOCUS=%d SHOT=%d REC=%d",
        st->ch[0], st->ch[1], st->ch[2], st->ch[3], st->ch[4], st->ch[5],
        st->mode, st->btn, st->stop, st->focus, st->shot, st->rec);

    if ((st->type == RC_AE || st->type == RC_APP_FUSED) && w > 0 && (size_t)w < n) {
        w += snprintf(out + w, n - (size_t)w,
            " C1=%d C2=%d C3=%d DIAL=%d RTH=%d UP=%d DN=%d L=%d R=%d AC=%d BACK=%d",
            st->c1, st->c2, st->c3, st->dial, st->rth,
            st->up, st->down, st->left, st->right, st->aircraft, st->back);
    }
    return w;
}

void rc_merge(const rc_state_t *a, int64_t age_a_us,
              const rc_state_t *b, int64_t age_b_us,
              int64_t stale_us, rc_state_t *out)
{
    memset(out, 0, sizeof(*out));

    /* 有数据且未超时才有资格参与融合 */
    const bool a_ok = (a->type != RC_NONE) && (age_a_us <= stale_us);
    const bool b_ok = (b->type != RC_NONE) && (age_b_us <= stale_us);

    /* 公共字段: 取更新鲜、有资格的一路 */
    const rc_state_t *common = NULL;
    if (a_ok && b_ok)
        common = (age_a_us <= age_b_us) ? a : b;
    else if (a_ok)
        common = a;
    else if (b_ok)
        common = b;

    if (common != NULL) {
        memcpy(out->ch, common->ch, sizeof(out->ch));
        out->mode  = common->mode;
        out->stop  = common->stop;
        out->focus = common->focus;
        out->shot  = common->shot;
        out->rec   = common->rec;
        out->type  = common->type;
    }

    /* RC/0xAE 专有字段: 取更新鲜、有资格的 RC/0xAE 一路;都失效则回中性(0) */
    const bool a_ae = (a->type == RC_AE) && (age_a_us <= stale_us);
    const bool b_ae = (b->type == RC_AE) && (age_b_us <= stale_us);
    const rc_state_t *ext = NULL;
    if (a_ae && b_ae)
        ext = (age_a_us <= age_b_us) ? a : b;
    else if (a_ae)
        ext = a;
    else if (b_ae)
        ext = b;

    if (ext != NULL) {
        out->btn = ext->btn;   /* 中心键只从 RC/0xAE 取(P20 的假 btn 不可信) */
        out->c1 = ext->c1; out->c2 = ext->c2; out->c3 = ext->c3;
        out->dial = ext->dial; out->rth = ext->rth;
        out->up = ext->up; out->down = ext->down;
        out->left = ext->left; out->right = ext->right;
        out->aircraft = ext->aircraft; out->back = ext->back;
        out->type = RC_AE;   /* 让 rc_state_to_kv 打印额外字段 */
    }
}
