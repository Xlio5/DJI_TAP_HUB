#include "adb_client.h"
#include "adb_getevent_rc.h"

#include <cstdlib>
#include <cstring>
#include <iostream>
#include <string>

static void expect(bool ok, const char *message)
{
    if (!ok) {
        std::cerr << "FAIL: " << message << "\n";
        std::exit(1);
    }
}

static void expectEq(int actual, int expected, const char *message)
{
    if (actual != expected) {
        std::cerr << "FAIL: " << message << " actual=" << actual
                  << " expected=" << expected << "\n";
        std::exit(1);
    }
}

int main()
{
    expectEq((int)adb_command("CNXN"), 0x4e584e43, "ADB command is little-endian");
    const uint8_t abc[] = {'a', 'b', 'c'};
    expectEq((int)adb_payload_checksum(abc, sizeof(abc)), 0x352441c2, "DJI TCP ADB checksum is CRC32");

    GeteventAbsEvent ev;
    expect(parse_getevent_abs_line("[ 1235.044742] /dev/input/event4: EV_ABS       ABS_RX               00007fff", &ev),
           "parse event4 ABS line");
    expect(ev.device == "/dev/input/event4", "device parsed");
    expect(ev.code == "ABS_RX", "axis code parsed");
    expectEq(ev.value, 32767, "positive hex value parsed");

    expect(parse_getevent_abs_line("[ 1235.044742] /dev/input/event4: EV_ABS       ABS_RY               fffff7da", &ev),
           "parse signed negative hex");
    expectEq(ev.value, -2086, "negative hex value parsed");

    rc_state_t st;
    std::memset(&st, 0, sizeof(st));
    st.type = RC_NONE;
    expect(apply_getevent_axis(ev, "/dev/input/event4", &st), "apply ABS_RY");
    expectEq(st.type, RC_APP_FUSED, "state marked as app fused");
    expectEq(st.ch[1], normalize_getevent_axis("ABS_RY", -2086), "ABS_RY maps to ch2");

    expect(parse_getevent_abs_line("[ 1235.044742] /dev/input/event4: EV_ABS       ABS_RZ               000000ff", &ev),
           "parse trigger axis");
    expect(apply_getevent_axis(ev, "/dev/input/event4", &st), "apply ABS_RZ");
    expectEq(st.ch[4], 660, "ABS_RZ trigger max maps to ch5");

    expect(parse_getevent_abs_line("[ 1235.044742] /dev/input/event3: EV_ABS       ABS_RX               00007fff", &ev),
           "parse non-event4 line");
    expect(!apply_getevent_axis(ev, "/dev/input/event4", &st), "ignore non-event4 axis for joystick state");
    expect(apply_getevent_axis(ev, "/dev/input/event3", &st), "custom axis device is honored");

    expect(!parse_getevent_abs_line("[ 1235.044742] /dev/input/event4: EV_SYN       SYN_REPORT           00000000", &ev),
           "ignore non-ABS line");

    expect(parse_getevent_abs_line("[ 4088.971127] EV_ABS       ABS_RX               ffffdf3a", &ev),
           "parse device-filtered getevent line without device prefix");
    expect(ev.device.empty(), "device-filtered getevent line has no device prefix");
    expect(ev.code == "ABS_RX", "axis code parsed without device prefix");
    expect(apply_getevent_axis(ev, "/dev/input/event4", &st),
           "device-filtered getevent line is accepted for selected device");

    std::cout << "adb_getevent_rc_test PASS\n";
    return 0;
}
