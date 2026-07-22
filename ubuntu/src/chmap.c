/* 通道映射实现 —— 见 chmap.h。纯 C,可主机单元测试。 */
#include "chmap.h"

/* 模拟摇杆: signed -660~+660 -> 1000~2000(中位 1500),越界夹紧 */
static uint16_t map_stick(int16_t v)
{
    if (v < -660) v = -660;
    if (v >  660) v =  660;
    return (uint16_t)(CH_MID + (int)v * 500 / 660);
}

/* 2档开关: 0->1000, 1->2000 */
static uint16_t sw2(uint8_t on)
{
    return on ? CH_MAX : CH_MIN;
}

void chmap_build(const rc_state_t *st, uint16_t out[CH_COUNT])
{
    /* CH1-6: 摇杆 */
    for (int i = 0; i < 6; i++)
        out[i] = map_stick(st->ch[i]);

    /* CH7: MODE (3档) */
    out[6] = (st->mode == 'S') ? CH_MIN :
             (st->mode == 'N') ? CH_MID :
             (st->mode == 'F') ? CH_MAX : CH_MID;

    out[7]  = sw2(st->rec);        /* CH8  REC */
    out[8]  = sw2(st->rth);        /* CH9  RTH */

    /* CH10: 快门 FOCUS/SHOT (松/半/全) */
    out[9]  = st->shot  ? CH_MAX :
              st->focus ? CH_MID : CH_MIN;

    out[10] = sw2(st->aircraft);   /* CH11 AIRCRAFT */

    /* CH12: DIAL 0~255 -> 1000~2000 */
    out[11] = (uint16_t)(CH_MIN + (int)st->dial * 1000 / 255);

    out[12] = sw2(st->stop);       /* CH13 STOP */

    /* CH14: C1+C2 混合 (4档) 无=1000 / C1=1333 / C2=1667 / C1+C2=2000 */
    {
        static const uint16_t c12_lvl[4] = { 1000, 1333, 1667, 2000 };
        int lvl = ((st->c2 & 1) << 1) | (st->c1 & 1);   /* 0..3 */
        out[13] = c12_lvl[lvl];
    }

    out[14] = sw2(st->c3);         /* CH15 C3 */

    /* CH16: 方向键 + BTN 混合 (6档,一次一个,优先级 BTN>UP>DN>L>R) */
    out[15] = st->btn   ? 2000 :
              st->up    ? 1200 :
              st->down  ? 1400 :
              st->left  ? 1600 :
              st->right ? 1800 : (uint16_t)CH_MIN;
}
