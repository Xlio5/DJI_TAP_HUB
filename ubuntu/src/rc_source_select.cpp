#include "rc_source_select.h"

#include <cstring>

static bool rc_valid_within(const rc_state_t &st, int64_t age_us, int64_t limit_us)
{
    return st.type != RC_NONE && age_us >= 0 && age_us <= limit_us;
}

RcSourceDecision rc_select_priority_source(const rc_state_t &p20, int64_t age20_us,
                                           const rc_state_t &p0, int64_t age0_us,
                                           int64_t p20_hold_us,
                                           int64_t stale_us)
{
    RcSourceDecision decision = {};
    decision.active = RcActiveSource::None;
    std::memset(&decision.state, 0, sizeof(decision.state));

    if (rc_valid_within(p20, age20_us, p20_hold_us)) {
        decision.active = RcActiveSource::P20_921600;
        decision.state = p20;
        return decision;
    }
    if (rc_valid_within(p0, age0_us, stale_us)) {
        decision.active = RcActiveSource::P0_115200;
        decision.state = p0;
        return decision;
    }
    return decision;
}

const char *rc_active_source_name(RcActiveSource src)
{
    switch (src) {
        case RcActiveSource::P20_921600: return "921600";
        case RcActiveSource::P0_115200:  return "115200";
        default:                         return "none";
    }
}
