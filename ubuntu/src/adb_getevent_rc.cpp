#include "adb_getevent_rc.h"

#include <algorithm>
#include <cctype>
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

int32_t parse_dec_i32(const std::string &s, bool *ok)
{
    errno = 0;
    char *end = nullptr;
    long v = std::strtol(s.c_str(), &end, 10);
    *ok = errno == 0 && end != s.c_str() && *end == '\0';
    return (int32_t)v;
}

std::string trim_copy(const std::string &s)
{
    size_t first = 0;
    while (first < s.size() && std::isspace((unsigned char)s[first])) first++;
    size_t last = s.size();
    while (last > first && std::isspace((unsigned char)s[last - 1])) last--;
    return s.substr(first, last - first);
}

bool parse_getevent_lp_abs_line(const std::string &line, GeteventAbsEvent *event)
{
    std::string s = trim_copy(line);
    if (s.find("ABS_") != 0) return false;

    size_t colon = s.find(':');
    if (colon == std::string::npos) return false;
    std::string code = trim_copy(s.substr(0, colon));
    if (axis_index(code) < 0) return false;

    size_t value_pos = s.find("value", colon + 1);
    if (value_pos == std::string::npos) return false;
    value_pos += 5;
    while (value_pos < s.size() && std::isspace((unsigned char)s[value_pos])) value_pos++;
    size_t value_end = value_pos;
    if (value_end < s.size() && (s[value_end] == '-' || s[value_end] == '+')) value_end++;
    while (value_end < s.size() && std::isdigit((unsigned char)s[value_end])) value_end++;
    if (value_end == value_pos) return false;

    bool ok = false;
    int32_t parsed = parse_dec_i32(s.substr(value_pos, value_end - value_pos), &ok);
    if (!ok) return false;

    event->device.clear();
    event->code = code;
    event->value = parsed;
    return true;
}

int16_t clamp_axis(int value)
{
    if (value < -660) return -660;
    if (value > 660) return 660;
    return (int16_t)value;
}

}  // namespace

std::string build_getevent_shell(const std::string &device, bool snapshot_axes)
{
    if (snapshot_axes) {
        return "getevent -lp " + device + "; exec getevent -lt " + device;
    }
    return "exec getevent -lt " + device;
}

bool parse_getevent_abs_line(const std::string &line, GeteventAbsEvent *event)
{
    if (!event) return false;
    *event = GeteventAbsEvent{};
    if (line.find("EV_ABS") == std::string::npos) {
        return parse_getevent_lp_abs_line(line, event);
    }

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
    if (ev.empty() || code.empty() || value.empty()) return false;
    bool ok = false;
    int32_t parsed = parse_hex_i32(value, &ok);
    if (!ok) return false;

    event->device = device;
    event->code = code;
    event->value = parsed;
    return true;
}

bool parse_getevent_key_line(const std::string &line, GeteventAbsEvent *event)
{
    if (!event || line.find("EV_KEY") == std::string::npos) return false;
    *event = GeteventAbsEvent{};
    std::istringstream in(line);
    std::string tok;
    while (in >> tok) {
        if (!tok.empty() && tok[0] == '/' && tok.find("/dev/input/event") == 0) {
            event->device = tok;
            if (!event->device.empty() && event->device.back() == ':') event->device.pop_back();
        }
        if (tok != "EV_KEY") continue;
        std::string value;
        if (!(in >> event->code >> value)) return false;
        if (event->code != "BTN_TL" && event->code != "BTN_TR" &&
            event->code != "KEY_F1" && event->code != "KEY_F2" &&
            event->code != "KEY_F3" && event->code != "KEY_F4" &&
            event->code != "KEY_F5" && event->code != "KEY_F6") return false;
        if (value == "DOWN") event->value = 1;
        else if (value == "UP") event->value = 0;
        else {
            bool ok = false;
            event->value = parse_hex_i32(value, &ok);
            if (!ok) return false;
            event->value = event->value != 0 ? 1 : 0;
        }
        return true;
    }
    return false;
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

bool apply_getevent_axis(const GeteventAbsEvent &event, const std::string &axis_device,
                         rc_state_t *state)
{
    if (!state) return false;
    if (!event.device.empty() && event.device != axis_device) return false;
    int idx = axis_index(event.code);
    if (idx < 0) return false;
    state->type = RC_APP_FUSED;
    if (state->mode == '\0') state->mode = '?';
    state->ch[idx] = normalize_getevent_axis(event.code, event.value);
    return true;
}

bool apply_getevent_key(const GeteventAbsEvent &event, const std::string &key_device,
                        rc_state_t *state)
{
    if (!state) return false;
    if (!key_device.empty() && !event.device.empty() && event.device != key_device) return false;
    if (event.code == "BTN_TL") state->rec = event.value != 0;
    else if (event.code == "BTN_TR") state->shot = event.value != 0;
    else if (event.code == "KEY_F1") state->l1 = event.value != 0;
    else if (event.code == "KEY_F2") state->l2 = event.value != 0;
    else if (event.code == "KEY_F3") state->l3 = event.value != 0;
    else if (event.code == "KEY_F4") state->r1 = event.value != 0;
    else if (event.code == "KEY_F5") state->r2 = event.value != 0;
    else if (event.code == "KEY_F6") state->r3 = event.value != 0;
    else return false;
    state->type = RC_APP_FUSED;
    if (state->mode == '\0') state->mode = '?';
    return true;
}
