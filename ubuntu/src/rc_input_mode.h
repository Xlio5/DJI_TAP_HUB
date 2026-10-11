#pragma once

#include <string_view>

enum class RcInputMode {
    AndroidFusion,
    V3sSerial,
    V3sAdb,
};

enum class RcInputSource {
    None,
    Android,
    Serial,
    Adb,
};

RcInputMode parse_rc_input_mode(std::string_view value);
const char *rc_input_mode_name(RcInputMode mode);
RcInputSource select_rc_input(RcInputMode mode, bool android_fresh,
                              bool serial_fresh, bool adb_fresh);
