#include "rc_source_select.h"

#include <iostream>

static int failures = 0;

static rc_state_t makeState(rc_type_t type, int16_t ch1)
{
    rc_state_t st = {};
    st.type = type;
    st.ch[0] = ch1;
    st.mode = 'N';
    return st;
}

static void expectSource(RcActiveSource actual, RcActiveSource expected, const char *message)
{
    if (actual != expected) {
        std::cerr << "FAIL: " << message << "\n";
        failures++;
    }
}

static void expectCh1(const rc_state_t &actual, int16_t expected, const char *message)
{
    if (actual.ch[0] != expected) {
        std::cerr << "FAIL: " << message << ": expected " << expected
                  << ", got " << actual.ch[0] << "\n";
        failures++;
    }
}

int main()
{
    rc_state_t p20 = makeState(RC_AE, 921);
    rc_state_t p0 = makeState(RC_SPECIAL, 115);

    RcSourceDecision d = rc_select_priority_source(p20, 49'000, p0, 1'000, 50'000, 500'000);
    expectSource(d.active, RcActiveSource::P20_921600, "921600 source wins inside 50ms window");
    expectCh1(d.state, 921, "921600 state is selected");

    d = rc_select_priority_source(p20, 50'001, p0, 1'000, 50'000, 500'000);
    expectSource(d.active, RcActiveSource::P0_115200, "115200 source wins after 921600 timeout");
    expectCh1(d.state, 115, "115200 state is selected");

    d = rc_select_priority_source(makeState(RC_NONE, 0), 0, p0, 10'000, 50'000, 500'000);
    expectSource(d.active, RcActiveSource::P0_115200, "115200 source works when 921600 has no RC");

    d = rc_select_priority_source(p20, 60'000, p0, 600'000, 50'000, 500'000);
    expectSource(d.active, RcActiveSource::None, "no source selected when both are stale by policy");

    return failures == 0 ? 0 : 1;
}
