#include "rc_input_mode.h"

#include <iostream>

static int failures = 0;

static void expect(bool value, const char *message) {
    if (!value) { std::cerr << "FAIL: " << message << "\n"; ++failures; }
}

int main() {
    expect(parse_rc_input_mode("android_fusion") == RcInputMode::AndroidFusion, "parse android");
    expect(parse_rc_input_mode("v3s_serial") == RcInputMode::V3sSerial, "parse serial");
    expect(parse_rc_input_mode("v3s_adb") == RcInputMode::V3sAdb, "parse adb");
    expect(parse_rc_input_mode("") == RcInputMode::V3sAdb, "empty defaults adb");
    expect(parse_rc_input_mode("bad") == RcInputMode::V3sAdb, "invalid defaults adb");
    expect(is_valid_rc_input_mode("android_fusion"), "android mode valid");
    expect(is_valid_rc_input_mode("v3s_serial"), "serial mode valid");
    expect(is_valid_rc_input_mode("v3s_adb"), "adb mode valid");
    expect(!is_valid_rc_input_mode("bad"), "invalid mode rejected");

    expect(select_rc_input(RcInputMode::AndroidFusion, true, true, true) == RcInputSource::Android,
           "android mode selects android");
    expect(select_rc_input(RcInputMode::AndroidFusion, false, true, true) == RcInputSource::None,
           "android mode does not fall back");
    expect(select_rc_input(RcInputMode::V3sSerial, true, true, true) == RcInputSource::Serial,
           "serial mode selects serial");
    expect(select_rc_input(RcInputMode::V3sSerial, true, false, true) == RcInputSource::None,
           "serial mode does not fall back");
    expect(select_rc_input(RcInputMode::V3sAdb, true, true, true) == RcInputSource::Adb,
           "adb mode selects adb");
    expect(select_rc_input(RcInputMode::V3sAdb, true, true, false) == RcInputSource::None,
           "adb mode does not fall back");
    return failures == 0 ? 0 : 1;
}
