package com.tunnathub.app.rc;

import java.util.Arrays;

public final class RcFusionEngineTest {
    public static void main(String[] args) {
        freshGeteventAxesOverride40007Axes();
        staleGeteventFallsBackTo40007Axes();
        keysComeFrom40007AndEventKeysComeFromGetevent();
        publishGateKeepsFixedIntervalOutput();
    }

    private static void freshGeteventAxesOverride40007Axes() {
        RcInputSample ge = RcInputSample.axes("getevent", Arrays.asList(10, 20, 30, 40, 50, 60), 1_000L);
        RcInputSample p4 = RcInputSample.full("40007", Arrays.asList(1, 2, 3, 4, 5, 6), 1, 0, 1, 0, 1, 0, "N", 990L);
        RcInputSample out = RcFusionEngine.fuse(ge, p4, 1_020L);
        assertEquals(10, out.getAxes().get(0).intValue(), "CH1 from getevent");
        assertEquals(60, out.getAxes().get(5).intValue(), "CH6 from getevent");
        assertEquals(1, out.getStop(), "STOP from 40007");
        assertEquals("N", out.getMode(), "mode from 40007");
    }

    private static void staleGeteventFallsBackTo40007Axes() {
        RcInputSample ge = RcInputSample.axes("getevent", Arrays.asList(10, 20, 30, 40, 50, 60), -4_001L);
        RcInputSample p4 = RcInputSample.full("40007", Arrays.asList(1, 2, 3, 4, 5, 6), 0, 1, 0, 1, 0, 1, "S", 990L);
        RcInputSample out = RcFusionEngine.fuse(ge, p4, 1_100L);
        assertEquals(1, out.getAxes().get(0).intValue(), "CH1 fallback to 40007");
        assertEquals(6, out.getAxes().get(5).intValue(), "CH6 fallback to 40007");
        assertEquals(1, out.getRec(), "REC from 40007");
    }

    private static void keysComeFrom40007AndEventKeysComeFromGetevent() {
        RcInputSample ge = RcInputSample.complete(
            "getevent", Arrays.asList(100, 100, 100, 100, 100, 100),
            0, 0, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
            1, 0, 0, 0, 0, 1, 0, "?", 1_000L
        );
        RcInputSample p4 = RcInputSample.full("40007", Arrays.asList(0, 0, 0, 0, 0, 0), 1, 1, 0, 0, 1, 1, "F", 1_000L);
        RcInputSample out = RcFusionEngine.fuse(ge, p4, 1_000L);
        assertEquals(1, out.getStop(), "STOP from 40007");
        assertEquals(1, out.getFocus(), "FOCUS from 40007");
        assertEquals(1, out.getShot(), "SHOT override from getevent");
        assertEquals(1, out.getRec(), "REC override from getevent");
        assertEquals(1, out.getL1(), "L1 from getevent");
        assertEquals(1, out.getR3(), "R3 from getevent");
    }

    private static void publishGateKeepsFixedIntervalOutput() {
        assertEquals(false, RcFusionEngine.shouldPublish(100L, 119L, 20L), "not yet");
        assertEquals(true, RcFusionEngine.shouldPublish(100L, 120L, 20L), "publish at interval");
        assertEquals(true, RcFusionEngine.shouldPublish(100L, 140L, 20L), "publish after interval");
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
