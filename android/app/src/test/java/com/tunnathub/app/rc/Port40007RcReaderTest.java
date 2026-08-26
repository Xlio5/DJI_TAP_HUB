package com.tunnathub.app.rc;

public final class Port40007RcReaderTest {
    public static void main(String[] args) {
        parsesSpecialControlProto();
        parsesVirtualStickProto();
        parsesCompactFallbackPacket();
    }

    private static void parsesSpecialControlProto() {
        byte[] packet = new byte[] {
            0x18, 0x01,                   // record = 1
            0x28, (byte) 0x80, 0x01,      // channel0 = 128
            0x30, (byte) 0xff, 0x01,      // channel1 = 255
            0x38, 0x00,                   // channel2 = 0
            0x40, (byte) 0x80, 0x01,      // channel3 = 128
            0x48, (byte) 0x80, 0x01,      // channel4 = 128
            0x50, (byte) 0x80, 0x01,      // channel5 = 128
            (byte) 0x90, 0x01, 0x01,      // shutter = 1
            (byte) 0x98, 0x01, 0x01,      // focus = 1
            (byte) 0xa0, 0x01, 0x01       // mode_sw = 1
        };
        RcInputSample sample = Port40007RcReader.parseSpecialControlProto(packet, 1_000L);
        if (sample == null) throw new AssertionError("special sample null");
        assertEquals(0, sample.getAxes().get(0).intValue(), "channel0 center");
        assertEquals(1016, sample.getAxes().get(1).intValue(), "channel1 high");
        assertEquals(-1024, sample.getAxes().get(2).intValue(), "channel2 low");
        assertEquals(1, sample.getRec(), "record");
        assertEquals(1, sample.getShot(), "shutter");
        assertEquals(1, sample.getFocus(), "focus");
        assertEquals("N", sample.getMode(), "mode");
    }

    private static void parsesVirtualStickProto() {
        byte[] packet = concat(
            fixed32(2, 30.0f),
            fixed32(3, -30.0f),
            fixed32(4, 90.0f),
            fixed32(5, 5.0f)
        );
        RcInputSample sample = Port40007RcReader.parseVirtualStickProto(packet, 2_000L);
        if (sample == null) throw new AssertionError("virtual sample null");
        assertEquals(1024, sample.getAxes().get(0).intValue(), "roll");
        assertEquals(-1024, sample.getAxes().get(1).intValue(), "pitch");
        assertEquals(512, sample.getAxes().get(2).intValue(), "yaw");
        assertEquals(1024, sample.getAxes().get(3).intValue(), "throttle");
    }

    private static void parsesCompactFallbackPacket() {
        byte[] packet = new byte[] {
            0x00, 0x00,
            0x00, 0x04, 0x00, 0x04, 0x00, 0x04, 0x00, 0x04, 0x00, 0x04, 0x00, 0x04,
            0x09, 0x01
        };
        RcInputSample sample = Port40007RcReader.parseCompactBytes(packet, 3_000L);
        if (sample == null) throw new AssertionError("compact sample null");
        assertEquals(0, sample.getAxes().get(0).intValue(), "CH1 center");
        assertEquals(1, sample.getStop(), "STOP");
        assertEquals(1, sample.getRec(), "REC");
        assertEquals("N", sample.getMode(), "mode");
    }

    private static byte[] fixed32(int field, float value) {
        int bits = Float.floatToIntBits(value);
        return new byte[] {
            (byte) ((field << 3) | 5),
            (byte) (bits & 0xff),
            (byte) ((bits >> 8) & 0xff),
            (byte) ((bits >> 16) & 0xff),
            (byte) ((bits >> 24) & 0xff)
        };
    }

    private static byte[] concat(byte[]... arrays) {
        int len = 0;
        for (byte[] a : arrays) len += a.length;
        byte[] out = new byte[len];
        int off = 0;
        for (byte[] a : arrays) {
            System.arraycopy(a, 0, out, off, a.length);
            off += a.length;
        }
        return out;
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
