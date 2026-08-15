package com.tunnathub.app;

import java.util.List;

public final class ChannelConfigWorkbenchTest {
    public static void main(String[] args) {
        normalizesMapToSixteenChannels();
        clampsAndOrdersRangeValues();
        mapsSourceToStickRangeKeys();
        mapsSwitchSourceToOnOffKeys();
        usesFirmwareDefaultChannelMap();
        detectsSrcCfgSupportFromResponse();
        labelsKnownSourcesForTheWorkbench();
    }

    private static void normalizesMapToSixteenChannels() {
        List<String> result = MainActivityKt.channelMapToListForTest("ch1,ch3,mode");
        assertEquals(16, result.size(), "normalized map size");
        assertEquals("ch1", result.get(0), "CH1 source");
        assertEquals("ch3", result.get(1), "CH2 source");
        assertEquals("mode", result.get(2), "CH3 source");
        assertEquals("none", result.get(15), "CH16 fallback");

        String joined = MainActivityKt.channelMapToStringForTest(result);
        assertEquals("ch1,ch3,mode,none,none,none,none,none,none,none,none,none,none,none,none,none", joined, "joined map");
    }

    private static void clampsAndOrdersRangeValues() {
        int[] ordered = MainActivityKt.sanitizeChannelRangeForTest(2300, 700);
        assertEquals(800, ordered[0], "range min clamp");
        assertEquals(2200, ordered[1], "range max clamp");

        int[] swapped = MainActivityKt.sanitizeChannelRangeForTest(1900, 1100);
        assertEquals(1100, swapped[0], "range swap min");
        assertEquals(1900, swapped[1], "range swap max");
    }

    private static void mapsSourceToStickRangeKeys() {
        String[] keys = MainActivityKt.sourceRangeKeysForTest("ch1");
        assertEquals("st1_min", keys[0], "stick min key");
        assertEquals("st1_max", keys[1], "stick max key");
        assertEquals("st1_mid", keys[2], "stick mid key");
        assertEquals("st1_rev", keys[3], "stick rev key");
    }

    private static void mapsSwitchSourceToOnOffKeys() {
        String[] keys = MainActivityKt.sourceRangeKeysForTest("rec");
        assertEquals("rec_off", keys[0], "switch off key");
        assertEquals("rec_on", keys[1], "switch on key");
        assertEquals("", keys[2], "switch mid key");
        assertEquals("", keys[3], "switch rev key");
    }

    private static void usesFirmwareDefaultChannelMap() {
        assertEquals(
            "ch1,ch2,ch3,ch4,ch5,ch6,mode,rec,rth,focus,aircraft,dial,stop,c12,c3,dir",
            MainActivityKt.defaultChannelMapForTest(),
            "firmware default map"
        );
    }

    private static void detectsSrcCfgSupportFromResponse() {
        assertEquals(true, MainActivityKt.responseSupportsSrcCfgForTest("{\"src_cfg_names\":\"st1_min\"}"), "src_cfg supported");
        assertEquals(false, MainActivityKt.responseSupportsSrcCfgForTest("{\"mode\":\"sbus\"}"), "src_cfg unsupported");
    }

    private static void labelsKnownSourcesForTheWorkbench() {
        assertEquals("J1", MainActivityKt.sourceDisplayLabelForTest("ch1"), "J1 label");
        assertEquals("飞行模式", MainActivityKt.sourceDisplayLabelForTest("mode"), "mode label");
        assertEquals("无", MainActivityKt.sourceDisplayLabelForTest("none"), "none label");
        assertEquals("custom", MainActivityKt.sourceDisplayLabelForTest("custom"), "custom passthrough");
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
