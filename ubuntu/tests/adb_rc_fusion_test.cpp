#include "adb_rc_fusion.h"

#include <cstdlib>
#include <cstring>
#include <iostream>

static void expect(bool ok, const char *message)
{
    if (!ok) {
        std::cerr << "FAIL: " << message << "\n";
        std::exit(1);
    }
}

static void expectEq(int actual, int expected, const char *message)
{
    if (actual != expected) {
        std::cerr << "FAIL: " << message << " actual=" << actual
                  << " expected=" << expected << "\n";
        std::exit(1);
    }
}

static rc_state_t make_state(rc_type_t type, int base)
{
    rc_state_t st;
    std::memset(&st, 0, sizeof(st));
    st.type = type;
    st.mode = '?';
    for (int i = 0; i < 6; i++) st.ch[i] = (int16_t)(base + i);
    return st;
}

int main()
{
    rc_state_t ge = make_state(RC_APP_FUSED, 100);
    rc_state_t p40007 = make_state(RC_AE, 200);
    p40007.mode = 'N';
    p40007.dial = 77;
    p40007.shot = 1;
    p40007.rec = 1;
    p40007.c1 = 1;

    rc_state_t fused{};
    adb_rc_fuse(&ge, 20000, &p40007, 20000, &fused);
    expectEq(fused.type, RC_APP_FUSED, "fresh fusion uses app fused type");
    expectEq(fused.ch[0], 100, "fresh getevent axis wins ch1");
    expectEq(fused.ch[5], 105, "fresh getevent axis wins ch6");
    expectEq(fused.mode, 'N', "40007 supplies mode");
    expectEq(fused.dial, 77, "40007 supplies dial");
    expectEq(fused.shot, 1, "40007 supplies shot");
    expectEq(fused.rec, 1, "40007 supplies rec");
    expectEq(fused.c1, 1, "40007 supplies C1");

    adb_rc_fuse(&ge, ADB_RC_GETEVENT_FRESH_US + 1, &p40007, 20000, &fused);
    expectEq(fused.ch[0], 200, "stale getevent falls back to 40007 axis");
    expectEq(fused.ch[5], 205, "40007 fallback supplies all axes");

    adb_rc_fuse(&ge, 20000, &p40007, ADB_RC_40007_FRESH_US + 1, &fused);
    expectEq(fused.ch[0], 100, "stale 40007 still allows getevent axes");
    expectEq(fused.mode, '?', "stale 40007 does not provide mode");
    expectEq(fused.c1, 0, "stale 40007 does not provide buttons");

    adb_rc_fuse(&ge, ADB_RC_GETEVENT_FRESH_US + 1,
                &p40007, ADB_RC_40007_FRESH_US + 1, &fused);
    expect(fused.type == RC_NONE, "all stale sources yield RC_NONE");

    std::cout << "adb_rc_fusion_test PASS\n";
    return 0;
}
