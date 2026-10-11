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
    expectEq(fused.shot, 0, "fresh getevent release overrides 40007 SHOT");
    expectEq(fused.rec, 0, "fresh getevent release overrides 40007 REC");
    expectEq(fused.c1, 1, "40007 supplies C1");

    ge.l1 = 1;
    ge.r3 = 1;
    adb_rc_fuse(&ge, 20000, &p40007, 20000, &fused);
    expectEq(fused.l1, 1, "getevent supplies L1");
    expectEq(fused.r3, 1, "getevent supplies R3");
    ge.l1 = 0;
    ge.r3 = 0;

    ge.rec = 1;
    p40007.rec = 0;
    adb_rc_fuse(&ge, 20000, &p40007, 20000, &fused);
    expectEq(fused.rec, 1, "fresh getevent supplies REC");
    ge.rec = 0;
    p40007.rec = 1;

    rc_state_t special = make_state(RC_SPECIAL, 300);
    special.mode = 'F';
    special.shot = 1;
    rc_state_t merged40007{};
    adb_rc_merge_40007_state(&p40007, &special, &merged40007);
    expectEq(merged40007.type, RC_AE, "special packet keeps AE extended state type");
    expectEq(merged40007.c1, 1, "special packet does not clear AE C1");
    expectEq(merged40007.dial, 77, "special packet does not clear AE dial");
    expectEq(merged40007.shot, 1, "special packet updates common shot");
    expectEq(merged40007.mode, 'F', "special packet updates common mode");

    merged40007.rec = 1;
    merged40007.shot = 1;
    merged40007.stop = 1;
    adb_rc_strip_getevent_owned_buttons(&merged40007);
    expectEq(merged40007.rec, 0, "40007 REC is removed before edge tracking");
    expectEq(merged40007.shot, 0, "40007 SHOT is removed before edge tracking");
    expectEq(merged40007.stop, 1, "40007 STOP remains available");

    AdbRcEdgeQueue edgeQueue{};
    rc_state_t released = make_state(RC_APP_FUSED, 100);
    expect(!adb_rc_queue_button_change(&edgeQueue, &released),
           "first state establishes edge baseline");
    rc_state_t pressed = released;
    pressed.rec = 1;
    expect(adb_rc_queue_button_change(&edgeQueue, &pressed), "REC down is queued");
    expect(adb_rc_queue_button_change(&edgeQueue, &released), "REC up is queued");
    rc_state_t edge{};
    expect(adb_rc_pop_button_change(&edgeQueue, &edge), "pop REC down");
    expectEq(edge.rec, 1, "REC down remains first");
    expect(adb_rc_pop_button_change(&edgeQueue, &edge), "pop REC up");
    expectEq(edge.rec, 0, "REC up remains second");
    expect(!adb_rc_pop_button_change(&edgeQueue, &edge), "edge queue is drained");

    AdbRcButtonTracker tracker{};
    released.c3 = 0;
    pressed = released;
    pressed.c3 = 1;
    expect(!adb_rc_track_button_change(&tracker, &released),
           "initial state establishes tracker baseline");
    expect(adb_rc_track_button_change(&tracker, &pressed),
           "C3 press is a direct edge");
    expect(!adb_rc_track_button_change(&tracker, &pressed),
           "repeated pressed state is not a direct edge");
    expect(adb_rc_track_button_change(&tracker, &released),
           "C3 release is a direct edge");

    expect(adb_rc_should_send_direct_edge(true, true, 4),
           "active V3S ADB edge is sent directly");
    expect(!adb_rc_should_send_direct_edge(false, true, 4),
           "unchanged buttons do not send directly");
    expect(!adb_rc_should_send_direct_edge(true, false, 4),
           "inactive input mode does not send directly");
    expect(!adb_rc_should_send_direct_edge(true, true, -1),
           "invalid RCMSG socket does not send directly");

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

    int64_t held_age = adb_rc_getevent_effective_age_us(true, true, 10000000, 1000);
    expectEq((int)held_age, 0, "connected getevent holds last axis state");

    int64_t disconnected_age = adb_rc_getevent_effective_age_us(false, true, 10000000, 1000);
    expect(disconnected_age > ADB_RC_GETEVENT_FRESH_US,
           "disconnected getevent does not hold stale axis state");

    int64_t missing_age = adb_rc_getevent_effective_age_us(true, false, 10000000, 1000);
    expect(missing_age > ADB_RC_GETEVENT_FRESH_US,
           "connected getevent without first state is not fresh");

    std::cout << "adb_rc_fusion_test PASS\n";
    return 0;
}
