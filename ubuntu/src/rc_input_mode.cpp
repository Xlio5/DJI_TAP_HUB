#include "rc_input_mode.h"

RcInputMode parse_rc_input_mode(std::string_view value) {
    if (value == "android_fusion") return RcInputMode::AndroidFusion;
    if (value == "v3s_serial") return RcInputMode::V3sSerial;
    return RcInputMode::V3sAdb;
}

const char *rc_input_mode_name(RcInputMode mode) {
    switch (mode) {
        case RcInputMode::AndroidFusion: return "android_fusion";
        case RcInputMode::V3sSerial: return "v3s_serial";
        case RcInputMode::V3sAdb: return "v3s_adb";
    }
    return "v3s_adb";
}

RcInputSource select_rc_input(RcInputMode mode, bool android_fresh,
                              bool serial_fresh, bool adb_fresh) {
    switch (mode) {
        case RcInputMode::AndroidFusion:
            return android_fresh ? RcInputSource::Android : RcInputSource::None;
        case RcInputMode::V3sSerial:
            return serial_fresh ? RcInputSource::Serial : RcInputSource::None;
        case RcInputMode::V3sAdb:
            return adb_fresh ? RcInputSource::Adb : RcInputSource::None;
    }
    return RcInputSource::None;
}
