/* rc_map 快门两段式映射测试: focus/shot 是同一个物理按键。 */
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

    for (int i = 0; i < CH_COUNT; i++) map[i] = SRC_NONE;
    map[0] = SRC_FOCUS;
    map[1] = SRC_SHOT;

    memset(&st, 0, sizeof(st));
    st.type = RC_AE;
    rc_map_build(&st, map, out);
    check_u16(out[0], 1000, "focus_release");
    check_u16(out[1], 1000, "shot_release");

    st.focus = 1;
    st.shot = 0;
    rc_map_build(&st, map, out);
    check_u16(out[0], 1500, "focus_half_press");
    check_u16(out[1], 1500, "shot_half_press");

    st.focus = 0;
    st.shot = 1;
    rc_map_build(&st, map, out);
    check_u16(out[0], 2000, "focus_full_press");
    check_u16(out[1], 2000, "shot_full_press");

    return g_fail ? 1 : 0;
}
