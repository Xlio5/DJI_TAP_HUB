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
    expect(build_getevent_shell("/dev/input/event4", true) ==
               "getevent -lp /dev/input/event4; exec getevent -lt /dev/input/event4",
           "joystick shell is restricted to event4");
    expect(build_getevent_shell("/dev/input/event3", false) ==
               "exec getevent -lt /dev/input/event3",
           "aux key shell is restricted to event3");

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

    expect(parse_getevent_key_line("[ 1235.044742] /dev/input/event4: EV_KEY       BTN_TL                DOWN", &ev),
           "parse REC key down");
    expect(apply_getevent_key(ev, "/dev/input/event4", &st), "apply REC key down");
    expectEq(st.rec, 1, "BTN_TL maps to REC");
    expect(parse_getevent_key_line("[ 1235.064742] /dev/input/event4: EV_KEY       BTN_TR                00000001", &ev),
           "parse SHOT numeric down");
    expect(apply_getevent_key(ev, "/dev/input/event4", &st), "apply SHOT key down");
    expectEq(st.shot, 1, "BTN_TR maps to SHOT");
    expect(parse_getevent_key_line("[ 1235.084742] /dev/input/event4: EV_KEY       BTN_TL                UP", &ev),
           "parse REC key up");
    expect(apply_getevent_key(ev, "/dev/input/event4", &st), "apply REC key up");
    expectEq(st.rec, 0, "REC releases on UP");

    expect(parse_getevent_key_line("[ 1235.104742] /dev/input/event3: EV_KEY       KEY_F1                DOWN", &ev),
           "parse event3 L1 key down");
    expect(apply_getevent_key(ev, "", &st), "apply key from any known device");
    expectEq(st.l1, 1, "KEY_F1 maps to L1");
    expect(parse_getevent_key_line("[ 1235.124742] /dev/input/event3: EV_KEY       KEY_F6                00000001", &ev),
           "parse event3 R3 numeric down");
    expect(apply_getevent_key(ev, "", &st), "apply R3 key from event3");
    expectEq(st.r3, 1, "KEY_F6 maps to R3");
    expect(!apply_getevent_key(ev, "/dev/input/event4", &st),
           "explicit event4 filter still rejects event3 keys");

    expect(parse_getevent_abs_line("[ 4088.971127] EV_ABS       ABS_RX               ffffdf3a", &ev),
           "parse device-filtered getevent line without device prefix");
    expect(ev.device.empty(), "device-filtered getevent line has no device prefix");
    expect(ev.code == "ABS_RX", "axis code parsed without device prefix");
    expect(apply_getevent_axis(ev, "/dev/input/event4", &st),
           "device-filtered getevent line is accepted for selected device");

    expect(parse_getevent_abs_line("    ABS_X                 : value 0, min -32768, max 32767, fuzz 16, flat 128, resolution 0", &ev),
           "parse getevent -lp ABS_X current value");
    expect(ev.device.empty(), "getevent -lp axis line has no device prefix");
    expect(ev.code == "ABS_X", "getevent -lp axis code parsed");
    expectEq(ev.value, 0, "getevent -lp neutral value parsed");

    expect(parse_getevent_abs_line("    ABS_Z                 : value 127, min 0, max 255, fuzz 0, flat 0, resolution 0", &ev),
           "parse getevent -lp trigger current value");
    expect(ev.code == "ABS_Z", "getevent -lp trigger code parsed");
    expectEq(ev.value, 127, "getevent -lp trigger value parsed");

    std::cout << "adb_getevent_rc_test PASS\n";
    return 0;
}
