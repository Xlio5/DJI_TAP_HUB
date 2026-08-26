package com.tunnathub.app.rc;

import com.tunnathub.app.RcMsg;
import java.util.Arrays;

public final class RcMsgCodecTest {
    public static void main(String[] args) {
        encodesPacketReadableByExistingRcMsgParser();
        clampsRawAxesToOutputChannels();
    }

    private static void encodesPacketReadableByExistingRcMsgParser() {
        RcInputSample sample = RcInputSample.complete(
            "getevent+40007",
            Arrays.asList(-1024, -512, 0, 512, 1024, 100),
            1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1,
            0, 0, 0, 0, 0, 0,
            88,
            "N",
            1_000L
        );
        byte[] packet = RcMsgCodec.encode(sample, 7, true, true);
        RcMsg.Data data = RcMsgCodec.decodeLocal(packet);
        if (data == null) throw new AssertionError("decoded null");
        assertEquals(RcMsg.LENGTH, packet.length, "packet length");
        assertEquals(1000, data.getChs().get(0).intValue(), "CH1 us");
        assertEquals(1500, data.getChs().get(2).intValue(), "CH3 us");
        assertEquals(2000, data.getChs().get(4).intValue(), "CH5 us");
        assertEquals(-1024, data.getRawChs().get(0).intValue(), "raw CH1");
        assertEquals(1, data.getBtn(), "BTN");
        assertEquals(1, data.getStop(), "STOP");
        assertEquals(1, data.getFocus(), "FOCUS");
        assertEquals(1, data.getShot(), "SHOT");
        assertEquals(1, data.getRec(), "REC");
        assertEquals(1, data.getRth(), "RTH");
        assertEquals(1, data.getC1(), "C1");
        assertEquals(1, data.getC2(), "C2");
        assertEquals(1, data.getC3(), "C3");
        assertEquals(1, data.getUp(), "UP");
        assertEquals(1, data.getDown(), "DOWN");
        assertEquals(1, data.getLeft(), "LEFT");
        assertEquals(1, data.getRight(), "RIGHT");
        assertEquals(1, data.getAircraft(), "AIRCRAFT");
        assertEquals(1, data.getBack(), "BACK");
        assertEquals(88, data.getDial(), "dial");
        assertEquals("N", data.getMode(), "mode");
    }

    private static void clampsRawAxesToOutputChannels() {
        assertEquals(1000, RcMsgCodec.rawToUs(-2000), "low clamp");
        assertEquals(1500, RcMsgCodec.rawToUs(0), "center");
        assertEquals(2000, RcMsgCodec.rawToUs(2000), "high clamp");
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
