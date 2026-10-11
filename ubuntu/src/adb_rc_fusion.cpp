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
        out->rec = getevent_state->rec;
        out->shot = getevent_state->shot;
        out->l1 = out->l1 || getevent_state->l1;
        out->l2 = out->l2 || getevent_state->l2;
        out->l3 = out->l3 || getevent_state->l3;
        out->r1 = out->r1 || getevent_state->r1;
        out->r2 = out->r2 || getevent_state->r2;
        out->r3 = out->r3 || getevent_state->r3;
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

void adb_rc_strip_getevent_owned_buttons(rc_state_t *state)
{
    if (!state) return;
    state->rec = 0;
    state->shot = 0;
}

static uint8_t rc_state_t::*const kButtonFields[] = {
    &rc_state_t::btn, &rc_state_t::stop, &rc_state_t::focus,
    &rc_state_t::shot, &rc_state_t::rec, &rc_state_t::rth,
    &rc_state_t::c1, &rc_state_t::c2, &rc_state_t::c3,
    &rc_state_t::up, &rc_state_t::down, &rc_state_t::left,
    &rc_state_t::right, &rc_state_t::aircraft, &rc_state_t::back,
    &rc_state_t::l1, &rc_state_t::l2, &rc_state_t::l3,
    &rc_state_t::r1, &rc_state_t::r2, &rc_state_t::r3,
};

static bool buttons_equal(const rc_state_t &a, const rc_state_t &b)
{
    for (size_t i = 0; i < sizeof(kButtonFields) / sizeof(kButtonFields[0]); ++i) {
        if (a.*kButtonFields[i] != b.*kButtonFields[i]) return false;
    }
    return true;
}

bool adb_rc_track_button_change(AdbRcButtonTracker *tracker,
                                const rc_state_t *state)
{
    if (!tracker || !state) return false;
    if (!tracker->has_last) {
        tracker->last = *state;
        tracker->has_last = true;
        return false;
    }
    const bool changed = !buttons_equal(tracker->last, *state);
    tracker->last = *state;
    return changed;
}

bool adb_rc_should_send_direct_edge(bool button_changed,
                                    bool v3s_adb_active, int rcmsg_fd)
{
    return button_changed && v3s_adb_active && rcmsg_fd >= 0;
}

bool adb_rc_queue_button_change(AdbRcEdgeQueue *queue, const rc_state_t *state)
{
    if (!queue || !state) return false;
    if (!queue->has_last) {
        queue->last = *state;
        queue->has_last = true;
        return false;
    }
    if (buttons_equal(queue->last, *state)) {
        queue->last = *state;
        return false;
    }
    queue->last = *state;
    if (queue->count == ADB_RC_EDGE_QUEUE_CAPACITY) {
        queue->head = (queue->head + 1) % ADB_RC_EDGE_QUEUE_CAPACITY;
        queue->count--;
    }
    size_t tail = (queue->head + queue->count) % ADB_RC_EDGE_QUEUE_CAPACITY;
    queue->items[tail] = *state;
    queue->count++;
    return true;
}

bool adb_rc_pop_button_change(AdbRcEdgeQueue *queue, rc_state_t *state)
{
    if (!queue || !state || queue->count == 0) return false;
    *state = queue->items[queue->head];
    queue->head = (queue->head + 1) % ADB_RC_EDGE_QUEUE_CAPACITY;
    queue->count--;
    return true;
}
