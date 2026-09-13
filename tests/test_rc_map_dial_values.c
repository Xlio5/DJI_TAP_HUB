/* rc_map DIAL/CH12 无极波轮默认值测试: 中位=1500, 左=1000, 右=2000。 */
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

int main(void)
{
    uint8_t map[CH_COUNT];
    uint16_t out[CH_COUNT];
    rc_state_t st;

    rc_map_set_cfg(NULL);
    for (int i = 0; i < CH_COUNT; i++) map[i] = SRC_NONE;
    map[0] = SRC_DIAL;

    memset(&st, 0, sizeof(st));
    st.type = RC_AE;

    st.dial = 0;
    rc_map_build(&st, map, out);
    check_u16(out[0], 1500, "dial_default_center");

    st.dial = 1;
    rc_map_build(&st, map, out);
    check_u16(out[0], 1000, "dial_left");

    st.dial = 130;
    rc_map_build(&st, map, out);
    check_u16(out[0], 1000, "dial_left_observed_raw");

    st.dial = 185;
    rc_map_build(&st, map, out);
    check_u16(out[0], 2000, "dial_right_observed_raw");

    st.dial = 255;
    rc_map_build(&st, map, out);
    check_u16(out[0], 2000, "dial_right");

    return g_fail ? 1 : 0;
}
