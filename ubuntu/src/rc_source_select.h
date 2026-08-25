#pragma once

#include <stdint.h>

extern "C" {
#include "rc_decode.h"
}

enum class RcActiveSource {
    None = 0,
    P20_921600,
    P0_115200,
};

struct RcSourceDecision {
    RcActiveSource active;
    rc_state_t state;
};

RcSourceDecision rc_select_priority_source(const rc_state_t &p20, int64_t age20_us,
                                           const rc_state_t &p0, int64_t age0_us,
                                           int64_t p20_hold_us,
                                           int64_t stale_us);

const char *rc_active_source_name(RcActiveSource src);
