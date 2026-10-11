package com.tunnathub.app;

import java.util.concurrent.atomic.AtomicLong;

public final class RcMsgUiPumpTest {
    public static void main(String[] args) {
        countsPacketsWithoutForcingUiApplyPerPacket();
        preservesButtonEdgesInOrder();
        samplesReceiveRateFromPacketCounter();
    }

    private static void preservesButtonEdgesInOrder() {
        AtomicLong now = new AtomicLong(1_000L);
        RcMsgUiPump<Integer> pump = new RcMsgUiPump<>(now::get);

        pump.notePacket(0, 0L);
        pump.notePacket(1, 1L);
        pump.notePacket(0, 0L);

        assertEquals(Integer.valueOf(1), pump.takeLatestForUi(), "button down edge first");
        assertEquals(Integer.valueOf(0), pump.takeLatestForUi(), "button up edge second");
    }

    private static void countsPacketsWithoutForcingUiApplyPerPacket() {
        AtomicLong now = new AtomicLong(1_000L);
        RcMsgUiPump<Integer> pump = new RcMsgUiPump<>(now::get);

        pump.notePacket(1);
        pump.notePacket(2);
        pump.notePacket(3);

        assertEquals(3, pump.getPacketCountForTest(), "packet count");
        assertEquals(Integer.valueOf(3), pump.takeLatestForUi(), "latest packet wins");
        assertEquals(null, pump.takeLatestForUi(), "latest packet consumed once");
    }

    private static void samplesReceiveRateFromPacketCounter() {
        AtomicLong now = new AtomicLong(1_000L);
        RcMsgUiPump<Integer> pump = new RcMsgUiPump<>(now::get);

        for (int i = 0; i < 50; i++) pump.notePacket(i);
        now.set(2_000L);

        float hz = pump.sampleReceiveHz();
        assertNear(50.0f, hz, 0.1f, "50 packets over 1s");

        for (int i = 0; i < 25; i++) pump.notePacket(i);
        now.set(2_500L);

        hz = pump.sampleReceiveHz();
        assertNear(50.0f, hz, 0.1f, "25 packets over 0.5s");
    }

    private static void assertEquals(Object expected, Object actual, String name) {
        if (expected == null ? actual != null : !expected.equals(actual)) {
            throw new AssertionError(name + " expected=" + expected + " actual=" + actual);
        }
    }

    private static void assertNear(float expected, float actual, float tolerance, String name) {
        if (Math.abs(expected - actual) > tolerance) {
            throw new AssertionError(name + " expected=" + expected + " actual=" + actual);
        }
    }
}
