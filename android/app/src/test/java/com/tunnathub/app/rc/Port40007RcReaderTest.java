package com.tunnathub.app.rc;

import java.io.ByteArrayInputStream;

public final class Port40007RcReaderTest {
    public static void main(String[] args) {
        parsesRealCapturedRcAePacket();
        parsesRcAeButtonsAndSwappedCh5Ch6();
        streamParserExtractsDumlAcrossChunks();
        rejectsShortPacket();
    }

    private static void parsesRealCapturedRcAePacket() {
        byte[] packet = hex("55 1e 04 8a 06 02 88 3f 00 06 ae 00 00 00 00 00 00 04 00 04 00 04 00 04 00 04 00 04 b1 23");
        RcInputSample sample = Port40007RcReader.parsePacket(packet, 1_000L);
        if (sample == null) throw new AssertionError("sample null");
        assertEquals("40007-rc-ae", sample.getSource(), "source");
        assertEquals(0, sample.getAxes().get(0).intValue(), "CH1 center");
        assertEquals(0, sample.getAxes().get(5).intValue(), "CH6 center");
        assertEquals("S", sample.getMode(), "mode");
    }

    private static void parsesRcAeButtonsAndSwappedCh5Ch6() {
        byte[] payload = new byte[] {
            (byte) 0xf0, (byte) 0xff, 0x1e, 0x00, 77,
            0x00, 0x04, 0x01, 0x04, 0x02, 0x04, 0x03, 0x04, 0x04, 0x04, 0x05, 0x04
        };
        RcInputSample sample = Port40007RcReader.parseRcAe(payload, 2_000L);
        if (sample == null) throw new AssertionError("sample null");
        assertEquals(1, sample.getFocus(), "FOCUS");
        assertEquals(1, sample.getShot(), "SHOT");
        assertEquals(1, sample.getRth(), "RTH");
        assertEquals(1, sample.getStop(), "STOP");
        assertEquals(1, sample.getRec(), "REC");
        assertEquals(1, sample.getBtn(), "BTN");
        assertEquals(1, sample.getC1(), "C1");
        assertEquals(1, sample.getC2(), "C2");
        assertEquals(1, sample.getC3(), "C3");
        assertEquals(5, sample.getAxes().get(4).intValue(), "CH5 swapped");
        assertEquals(4, sample.getAxes().get(5).intValue(), "CH6 swapped");
        assertEquals(77, sample.getDial(), "dial");
        assertEquals("F", sample.getMode(), "mode");
    }

    private static void streamParserExtractsDumlAcrossChunks() {
        byte[] packet = hex("55 1e 04 8a 06 02 88 3f 00 06 ae 00 00 00 00 00 00 04 00 04 00 04 00 04 00 04 00 04 b1 23");
        byte[] noisy = concat(new byte[] { 0x01, 0x02 }, packet);
        DumlStreamPacketSource source = new DumlStreamPacketSource(new ByteArrayInputStream(noisy));
        byte[] parsed = source.readPacket();
        if (parsed == null) throw new AssertionError("packet null");
        assertEquals(packet.length, parsed.length, "packet len");
        assertEquals(0x55, parsed[0] & 0xff, "sof");
    }

    private static void rejectsShortPacket() {
        if (Port40007RcReader.parsePacket(new byte[] { 1, 2, 3 }, 1_000L) != null) {
            throw new AssertionError("short packet should be rejected");
        }
    }

    private static byte[] concat(byte[] a, byte[] b) {
        byte[] out = new byte[a.length + b.length];
        System.arraycopy(a, 0, out, 0, a.length);
        System.arraycopy(b, 0, out, a.length, b.length);
        return out;
    }

    private static byte[] hex(String text) {
        String[] parts = text.split(" ");
        byte[] out = new byte[parts.length];
        for (int i = 0; i < parts.length; i++) {
            out[i] = (byte) Integer.parseInt(parts[i], 16);
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
