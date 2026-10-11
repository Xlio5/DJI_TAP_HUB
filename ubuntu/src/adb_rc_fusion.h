#pragma once

#include <cstddef>
#include <cstdint>

extern "C" {
#include "rc_decode.h"
}

constexpr int64_t ADB_RC_GETEVENT_FRESH_US = 5000000LL;
constexpr int64_t ADB_RC_40007_FRESH_US = 5000000LL;
constexpr size_t ADB_RC_EDGE_QUEUE_CAPACITY = 32;

struct AdbRcEdgeQueue {
    rc_state_t items[ADB_RC_EDGE_QUEUE_CAPACITY]{};
    rc_state_t last{};
    size_t head = 0;
    size_t count = 0;
    bool has_last = false;
};

int64_t adb_rc_getevent_effective_age_us(bool connected, bool has_state,
                                         int64_t now_us, int64_t last_us);

void adb_rc_fuse(const rc_state_t *getevent_state, int64_t getevent_age_us,
                 const rc_state_t *p40007_state, int64_t p40007_age_us,
                 rc_state_t *out);

void adb_rc_merge_40007_state(const rc_state_t *previous,
                              const rc_state_t *incoming, rc_state_t *out);
bool adb_rc_queue_button_change(AdbRcEdgeQueue *queue, const rc_state_t *state);
bool adb_rc_pop_button_change(AdbRcEdgeQueue *queue, rc_state_t *state);
