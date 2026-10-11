#include "adb_rc_fusion.h"

#include <cstring>
#include <climits>

int64_t adb_rc_getevent_effective_age_us(bool connected, bool has_state,
                                         int64_t now_us, int64_t last_us)
{
    if (!has_state || last_us <= 0) return INT64_MAX;
    if (connected) return 0;
    if (now_us < last_us) return INT64_MAX;
    return now_us - last_us;
}

void adb_rc_fuse(const rc_state_t *getevent_state, int64_t getevent_age_us,
                 const rc_state_t *p40007_state, int64_t p40007_age_us,
                 rc_state_t *out)
{
    if (!out) return;
    std::memset(out, 0, sizeof(*out));
    out->mode = '?';

    const bool ge_fresh = getevent_state && getevent_state->type != RC_NONE &&
                          getevent_age_us >= 0 &&
                          getevent_age_us <= ADB_RC_GETEVENT_FRESH_US;
    const bool p4_fresh = p40007_state && p40007_state->type != RC_NONE &&
                          p40007_age_us >= 0 &&
                          p40007_age_us <= ADB_RC_40007_FRESH_US;
    if (!ge_fresh && !p4_fresh) {
        out->type = RC_NONE;
        return;
    }

    out->type = RC_APP_FUSED;

    if (p4_fresh) {
        *out = *p40007_state;
        out->type = RC_APP_FUSED;
        if (out->mode != 'S' && out->mode != 'N' && out->mode != 'F') out->mode = '?';
    }

    if (ge_fresh) {
        for (int i = 0; i < 6; i++) out->ch[i] = getevent_state->ch[i];
        out->rec = out->rec || getevent_state->rec;
        out->shot = out->shot || getevent_state->shot;
        out->type = RC_APP_FUSED;
    }
}

void adb_rc_merge_40007_state(const rc_state_t *previous,
                              const rc_state_t *incoming, rc_state_t *out)
{
    if (!out) return;
    if (!incoming || incoming->type == RC_NONE) {
        if (previous) *out = *previous;
        else std::memset(out, 0, sizeof(*out));
        return;
    }
    if (incoming->type != RC_SPECIAL || !previous || previous->type != RC_AE) {
        *out = *incoming;
        return;
    }

    *out = *previous;
    std::memcpy(out->ch, incoming->ch, sizeof(out->ch));
    out->mode = incoming->mode;
    out->stop = incoming->stop;
    out->focus = incoming->focus;
    out->shot = incoming->shot;
    out->rec = incoming->rec;
}

void adb_rc_stretch_buttons(const rc_state_t *input, int64_t now_us,
                            AdbRcButtonHold *hold, rc_state_t *out)
{
    if (!out) return;
    if (!input || !hold) {
        std::memset(out, 0, sizeof(*out));
        return;
    }
    *out = *input;
    uint8_t rc_state_t::*fields[] = {
        &rc_state_t::btn, &rc_state_t::stop, &rc_state_t::focus,
        &rc_state_t::shot, &rc_state_t::rec, &rc_state_t::rth,
        &rc_state_t::c1, &rc_state_t::c2, &rc_state_t::c3,
        &rc_state_t::up, &rc_state_t::down, &rc_state_t::left,
        &rc_state_t::right, &rc_state_t::aircraft, &rc_state_t::back,
    };
    for (size_t i = 0; i < sizeof(fields) / sizeof(fields[0]); ++i) {
        if (input->*fields[i]) hold->until_us[i] = now_us + ADB_RC_BUTTON_HOLD_US;
        out->*fields[i] = (input->*fields[i] || now_us < hold->until_us[i]) ? 1 : 0;
    }
}
