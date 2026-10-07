#include "adb_getevent_rc.h"

#include <algorithm>
#include <cerrno>
#include <cstdlib>
#include <cstring>
#include <sstream>

namespace {

int axis_index(const std::string &code)
{
    if (code == "ABS_RX") return 0;
    if (code == "ABS_RY") return 1;
    if (code == "ABS_Y") return 2;
    if (code == "ABS_X") return 3;
    if (code == "ABS_RZ") return 4;
    if (code == "ABS_Z") return 5;
    return -1;
}

int32_t parse_hex_i32(const std::string &s, bool *ok)
{
    errno = 0;
    char *end = nullptr;
    unsigned long v = std::strtoul(s.c_str(), &end, 16);
    *ok = errno == 0 && end != s.c_str() && *end == '\0';
    return (int32_t)(uint32_t)v;
}

int16_t clamp_axis(int value)
{
    if (value < -660) return -660;
    if (value > 660) return 660;
    return (int16_t)value;
}

}  // namespace

bool parse_getevent_abs_line(const std::string &line, GeteventAbsEvent *event)
{
    if (!event) return false;
    if (line.find("EV_ABS") == std::string::npos) return false;

    std::istringstream in(line);
    std::string tok;
    std::string device;
    std::string ev;
    std::string code;
    std::string value;
    while (in >> tok) {
        if (!tok.empty() && tok[0] == '/' && tok.find("/dev/input/event") == 0) {
            device = tok;
            if (!device.empty() && device.back() == ':') device.pop_back();
        }
        if (tok == "EV_ABS") {
            ev = tok;
            in >> code >> value;
            break;
        }
    }
    if (device.empty() || ev.empty() || code.empty() || value.empty()) return false;
    bool ok = false;
    int32_t parsed = parse_hex_i32(value, &ok);
    if (!ok) return false;

    event->device = device;
    event->code = code;
    event->value = parsed;
    return true;
}

int16_t normalize_getevent_axis(const std::string &code, int32_t value)
{
    if (code == "ABS_Z" || code == "ABS_RZ") {
        int v = (int)value;
        if (v < 0) v = 0;
        if (v > 255) v = 255;
        return clamp_axis((v - 127) * 660 / 128);
    }
    int32_t v = value;
    if (v < -32768) v = -32768;
    if (v > 32767) v = 32767;
    return clamp_axis((int)(v * 660 / 32768));
}

bool apply_getevent_axis(const GeteventAbsEvent &event, rc_state_t *state)
{
    if (!state) return false;
    if (event.device != "/dev/input/event4") return false;
    int idx = axis_index(event.code);
    if (idx < 0) return false;
    state->type = RC_APP_FUSED;
    if (state->mode == '\0') state->mode = '?';
    state->ch[idx] = normalize_getevent_axis(event.code, event.value);
    return true;
}
