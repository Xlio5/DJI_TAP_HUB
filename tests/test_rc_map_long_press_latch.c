/* rc_map 长按锁存测试: RTH 长按确认后锁存, 短按恢复。 */
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "../ubuntu/src/rc_map.h"

static int g_fail = 0;

static void check_u16(uint16_t actual, uint16_t expected, const char *name)
{
    if (actual != expected) {
        printf("FAIL %s expected=%u actual=%u\n", name, expected, actual);
        g_fail++;
    } else {
        printf("OK %s=%u\n", name, actual);
    }
}

static void check_bool(int actual, int expected, const char *name)
{
    if (!!actual != !!expected) {
        printf("FAIL %s expected=%d actual=%d\n", name, !!expected, !!actual);
        g_fail++;
    } else {
        printf("OK %s=%d\n", name, !!actual);
    }
}

int main(void)
{
    uint8_t map[CH_COUNT];
    uint16_t out[CH_COUNT];
    rc_state_t st;
    rc_src_cfg_t cfg;

    for (int i = 0; i < CH_COUNT; i++) map[i] = SRC_NONE;
    map[0] = SRC_RTH;

    rc_cfg_defaults(&cfg);
    cfg.v[CFG_RTH_LP] = 1;
    rc_map_set_cfg(&cfg);
    rc_map_lp_reset_all();

    memset(&st, 0, sizeof(st));
    st.type = RC_AE;

    rc_map_build(&st, map, out);
    check_u16(out[0], 1000, "rth_initial_off");

    st.rth = 1;
    rc_map_lp_update(SRC_RTH, true, 1000000, 1000000);
    rc_map_build(&st, map, out);
    check_u16(out[0], 1000, "rth_short_press_does_not_trigger");

    st.rth = 0;
    rc_map_lp_update(SRC_RTH, false, 1200000, 1000000);
    rc_map_build(&st, map, out);
    check_u16(out[0], 1000, "rth_short_release_stays_off");
    check_bool(rc_map_lp_get(SRC_RTH), 0, "rth_latch_after_short");

    st.rth = 1;
    rc_map_lp_update(SRC_RTH, true, 2000000, 1000000);
    rc_map_lp_update(SRC_RTH, true, 2500000, 1000000);
    rc_map_build(&st, map, out);
    check_u16(out[0], 1000, "rth_half_second_press_still_off");
    rc_map_lp_update(SRC_RTH, true, 3000000, 1000000);
    rc_map_build(&st, map, out);
    check_u16(out[0], 2000, "rth_one_second_press_triggers_on");
    check_bool(rc_map_lp_get(SRC_RTH), 1, "rth_latch_after_long");

    st.rth = 0;
    rc_map_lp_update(SRC_RTH, false, 3100000, 1000000);
    rc_map_build(&st, map, out);
    check_u16(out[0], 2000, "rth_release_after_long_stays_latched");

    st.rth = 1;
    rc_map_lp_update(SRC_RTH, true, 3500000, 1000000);
    rc_map_build(&st, map, out);
    check_u16(out[0], 2000, "rth_short_press_while_latched_keeps_on");

    st.rth = 0;
    rc_map_lp_update(SRC_RTH, false, 3600000, 1000000);
    rc_map_build(&st, map, out);
    check_u16(out[0], 1000, "rth_short_release_clears_latch");
    check_bool(rc_map_lp_get(SRC_RTH), 0, "rth_latch_after_clear");

    return g_fail ? 1 : 0;
}
