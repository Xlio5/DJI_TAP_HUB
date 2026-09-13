/* rc_map MODE 三档默认值测试: N=1000, S=1500, F=2000。 */
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
    map[0] = SRC_MODE;

    memset(&st, 0, sizeof(st));
    st.type = RC_AE;

    st.mode = 'N';
    rc_map_build(&st, map, out);
    check_u16(out[0], 1000, "mode_n");

    st.mode = 'S';
    rc_map_build(&st, map, out);
    check_u16(out[0], 1500, "mode_s");

    st.mode = 'F';
    rc_map_build(&st, map, out);
    check_u16(out[0], 2000, "mode_f");

    return g_fail ? 1 : 0;
}
