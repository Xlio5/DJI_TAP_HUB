package com.tunnathub.app.rc;

public final class GetEventRcReaderTest {
    public static void main(String[] args) {
        parsesAxisLine();
        parsesKeyLine();
        normalizesWideAndByteAxes();
        exposesConfirmedDefaultAxisMap();
        exposesConfirmedDefaultKeyMap();
        buildsSampleWithRecShotAndLrKeys();
    }

    private static void parsesAxisLine() {
        GetEventRcReader.AxisEvent event =
            GetEventRcReader.parseAxisLine("[  123.456789] /dev/input/event4: EV_ABS ABS_X 00007fff");
        assertEquals("ABS_X", event.getCode(), "axis code");
        assertEquals(32767, event.getValue(), "axis value");

        GetEventRcReader.AxisEvent negative =
            GetEventRcReader.parseAxisLine("[  123.456790] /dev/input/event4: EV_ABS ABS_RX ffff8000");
        assertEquals(-32768, negative.getValue(), "signed hex value");
    }

    private static void parsesKeyLine() {
        GetEventRcReader.KeyEvent event =
            GetEventRcReader.parseKeyLine("[  123.456790] /dev/input/event4: EV_KEY KEY_RECORD DOWN");
        assertEquals("KEY_RECORD", event.getCode(), "key code");
        assertEquals(true, event.getPressed(), "key pressed");
    }

    private static void normalizesWideAndByteAxes() {
        assertEquals(1023, GetEventRcReader.normalizeAxis("ABS_X", 32767), "wide max");
        assertEquals(-1024, GetEventRcReader.normalizeAxis("ABS_Y", -32768), "wide min");
        assertEquals(0, GetEventRcReader.normalizeAxis("ABS_Z", 127), "byte mid");
        assertEquals(1024, GetEventRcReader.normalizeAxis("ABS_RZ", 255), "byte max");
    }

    private static void exposesConfirmedDefaultAxisMap() {
        assertEquals(0, GetEventRcReader.Companion.getDEFAULT_AXIS_MAP().get("ABS_RX").intValue(), "CH1 axis");
        assertEquals(1, GetEventRcReader.Companion.getDEFAULT_AXIS_MAP().get("ABS_RY").intValue(), "CH2 axis");
        assertEquals(2, GetEventRcReader.Companion.getDEFAULT_AXIS_MAP().get("ABS_Y").intValue(), "CH3 axis");
        assertEquals(3, GetEventRcReader.Companion.getDEFAULT_AXIS_MAP().get("ABS_X").intValue(), "CH4 axis");
        assertEquals(4, GetEventRcReader.Companion.getDEFAULT_AXIS_MAP().get("ABS_RZ").intValue(), "CH5 axis");
        assertEquals(5, GetEventRcReader.Companion.getDEFAULT_AXIS_MAP().get("ABS_Z").intValue(), "CH6 axis");
    }

    private static void exposesConfirmedDefaultKeyMap() {
        assertEquals("REC", GetEventRcReader.Companion.getDEFAULT_KEY_MAP().get("BTN_TL"), "REC key");
        assertEquals("SHOT", GetEventRcReader.Companion.getDEFAULT_KEY_MAP().get("BTN_TR"), "SHOT key");
        assertEquals("L1", GetEventRcReader.Companion.getDEFAULT_KEY_MAP().get("KEY_F1"), "L1 key");
        assertEquals("R3", GetEventRcReader.Companion.getDEFAULT_KEY_MAP().get("KEY_F6"), "R3 key");
    }

    private static void buildsSampleWithRecShotAndLrKeys() {
        java.util.Map<String, Integer> keys = new java.util.HashMap<>();
        keys.put("REC", 1);
        keys.put("SHOT", 1);
        keys.put("L1", 1);
        keys.put("R3", 1);
        RcInputSample sample = GetEventRcReader.sampleForTest(
            java.util.Arrays.asList(1, 2, 3, 4, 5, 6),
            keys,
            1_000L
        );
        assertEquals(1, sample.getRec(), "REC sample");
        assertEquals(1, sample.getShot(), "SHOT sample");
        assertEquals(1, sample.getL1(), "L1 sample");
        assertEquals(1, sample.getR3(), "R3 sample");
    }

    private static void assertEquals(Object expected, Object actual, String name) {
        if (!expected.equals(actual)) {
            throw new AssertionError(name + " expected=" + expected + " actual=" + actual);
        }
    }

    private static void assertEquals(int expected, int actual, String name) {
        if (expected != actual) {
            throw new AssertionError(name + " expected=" + expected + " actual=" + actual);
        }
    }
}
