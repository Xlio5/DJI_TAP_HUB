#pragma once

#include <cstdint>

extern "C" {
#include "rc_decode.h"
}

constexpr int64_t ADB_RC_GETEVENT_FRESH_US = 5000000LL;
constexpr int64_t ADB_RC_40007_FRESH_US = 5000000LL;

void adb_rc_fuse(const rc_state_t *getevent_state, int64_t getevent_age_us,
                 const rc_state_t *p40007_state, int64_t p40007_age_us,
                 rc_state_t *out);
