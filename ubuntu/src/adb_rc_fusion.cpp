#include "adb_rc_fusion.h"

#include <cstring>

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
        out->type = RC_APP_FUSED;
    }
}
