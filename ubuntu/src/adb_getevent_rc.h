#pragma once

#include <cstdint>
#include <string>

extern "C" {
#include "rc_decode.h"
}

struct GeteventAbsEvent {
    std::string device;
    std::string code;
    int32_t value = 0;
};

bool parse_getevent_abs_line(const std::string &line, GeteventAbsEvent *event);
bool parse_getevent_key_line(const std::string &line, GeteventAbsEvent *event);
int16_t normalize_getevent_axis(const std::string &code, int32_t value);
bool apply_getevent_axis(const GeteventAbsEvent &event, const std::string &axis_device,
                         rc_state_t *state);
bool apply_getevent_key(const GeteventAbsEvent &event, const std::string &key_device,
                        rc_state_t *state);
