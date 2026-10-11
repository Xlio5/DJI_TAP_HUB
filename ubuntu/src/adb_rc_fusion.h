#pragma once

#include <cstdint>

extern "C" {
#include "rc_decode.h"
}

constexpr int64_t ADB_RC_GETEVENT_FRESH_US = 5000000LL;
constexpr int64_t ADB_RC_40007_FRESH_US = 5000000LL;
constexpr int64_t ADB_RC_BUTTON_HOLD_US = 120000LL;

struct AdbRcButtonHold {
    int64_t until_us[15]{};
};

int64_t adb_rc_getevent_effective_age_us(bool connected, bool has_state,
                                         int64_t now_us, int64_t last_us);

void adb_rc_fuse(const rc_state_t *getevent_state, int64_t getevent_age_us,
                 const rc_state_t *p40007_state, int64_t p40007_age_us,
                 rc_state_t *out);

void adb_rc_merge_40007_state(const rc_state_t *previous,
                              const rc_state_t *incoming, rc_state_t *out);
void adb_rc_stretch_buttons(const rc_state_t *input, int64_t now_us,
                            AdbRcButtonHold *hold, rc_state_t *out);
