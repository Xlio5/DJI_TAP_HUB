package com.tunnathub.app.video;

public final class RtcpFeedbackTest {
    public static void main(String[] args) {
        buildsPliPacket();
        buildsFirPacket();
    }

    private static void buildsPliPacket() {
        byte[] pli = RtcpFeedback.buildPli(0x11223344, 0x55667788);
        assertEquals(12, pli.length, "pli length");
        assertEquals(0x81, pli[0] & 0xff, "pli v/fmt");
        assertEquals(206, pli[1] & 0xff, "pli pt");
        assertEquals(2, ((pli[2] & 0xff) << 8) | (pli[3] & 0xff), "pli words");
        assertEquals(0x11223344, readInt(pli, 4), "sender ssrc");
        assertEquals(0x55667788, readInt(pli, 8), "media ssrc");
    }

    private static void buildsFirPacket() {
        byte[] fir = RtcpFeedback.buildFir(0x11223344, 0x55667788, 7);
        assertEquals(20, fir.length, "fir length");
        assertEquals(0x84, fir[0] & 0xff, "fir v/fmt");
        assertEquals(206, fir[1] & 0xff, "fir pt");
        assertEquals(4, ((fir[2] & 0xff) << 8) | (fir[3] & 0xff), "fir words");
        assertEquals(0x11223344, readInt(fir, 4), "sender ssrc");
        assertEquals(0, readInt(fir, 8), "unused media ssrc");
        assertEquals(0x55667788, readInt(fir, 12), "fir media ssrc");
        assertEquals(7, fir[16] & 0xff, "fir seq");
    }

    private static int readInt(byte[] data, int offset) {
        return ((data[offset] & 0xff) << 24)
            | ((data[offset + 1] & 0xff) << 16)
            | ((data[offset + 2] & 0xff) << 8)
            | (data[offset + 3] & 0xff);
    }

    private static void assertEquals(int expected, int actual, String name) {
        if (expected != actual) {
            throw new AssertionError(name + " expected=" + expected + " actual=" + actual);
        }
    }
}
