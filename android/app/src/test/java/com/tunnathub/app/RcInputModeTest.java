package com.tunnathub.app;

import java.util.Arrays;
import java.util.List;

public final class RcInputModeTest {
    public static void main(String[] args) {
        parsesSavedModeWithAndroidFusionAsDefault();
        appliesV3sRcmsgAsFullRcInputWhenSelected();
        keepsAndroidFusionSplitChannelsWhenSelected();
    }

    private static void parsesSavedModeWithAndroidFusionAsDefault() {
        assertEquals(RcInputMode.ANDROID_FUSION, RcInputMode.Companion.fromPref(null), "null mode fallback");
        assertEquals(RcInputMode.ANDROID_FUSION, RcInputMode.Companion.fromPref("bad"), "bad mode fallback");
        assertEquals(RcInputMode.V3S_RCMSG, RcInputMode.Companion.fromPref("v3s_rcmsg"), "v3s mode parse");
    }

    private static void appliesV3sRcmsgAsFullRcInputWhenSelected() {
        List<Integer> current = Arrays.asList(
            1501, 1502, 1503, 1504, 1505, 1506, 1007, 1008,
            1009, 1010, 1011, 1012, 1013, 1014, 1015, 1016
        );
        List<Integer> incoming = Arrays.asList(
            1101, 1102, 1103, 1104, 1105, 1106, 1707, 1708,
            1709, 1710, 1711, 1712, 1713, 1714, 1715, 1716
        );

        List<Integer> result = RcInputModeKt.rcChannelsForIncomingDataForTest(
            current,
            incoming,
            RcInputMode.V3S_RCMSG,
            "V3S-RCMSG"
        );

        assertEquals(incoming, result, "v3s mode uses full rcmsg");
    }

    private static void keepsAndroidFusionSplitChannelsWhenSelected() {
        List<Integer> current = Arrays.asList(
            1501, 1502, 1503, 1504, 1505, 1506, 1007, 1008,
            1009, 1010, 1011, 1012, 1013, 1014, 1015, 1016
        );
        List<Integer> incoming = Arrays.asList(
            1101, 1102, 1103, 1104, 1105, 1106, 1707, 1708,
            1709, 1710, 1711, 1712, 1713, 1714, 1715, 1716
        );

        List<Integer> result = RcInputModeKt.rcChannelsForIncomingDataForTest(
            current,
            incoming,
            RcInputMode.ANDROID_FUSION,
            "V3S-RCMSG"
        );

        List<Integer> expected = Arrays.asList(
            1501, 1502, 1503, 1504, 1505, 1506, 1707, 1708,
            1709, 1710, 1711, 1712, 1713, 1714, 1715, 1716
        );
        assertEquals(expected, result, "android fusion keeps local sticks and v3s mapped channels");
    }

    private static void assertEquals(Object expected, Object actual, String name) {
        if (!expected.equals(actual)) {
            throw new AssertionError(name + " expected=" + expected + " actual=" + actual);
        }
    }
}
