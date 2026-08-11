package com.tunnathub.app.video;

import java.util.List;

public final class H264AccessUnitAssemblerTest {
    public static void main(String[] args) {
        emitsOneAccessUnitForMultipleNalsWithSameTimestamp();
        flushesPreviousTimestampBeforeStartingNextAccessUnit();
    }

    private static void emitsOneAccessUnitForMultipleNalsWithSameTimestamp() {
        H264AccessUnitAssembler assembler = new H264AccessUnitAssembler();
        byte[] sei = annexB(6, 0x11);
        byte[] idr = annexB(5, 0x22, 0x33);

        List<H264AccessUnitAssembler.AccessUnit> first = assembler.addNal(sei, 90_000L, 100L, 6, false);
        if (!first.isEmpty()) throw new AssertionError("non-marker nal should not emit AU");

        List<H264AccessUnitAssembler.AccessUnit> second = assembler.addNal(idr, 90_000L, 120L, 5, true);
        assertEquals(1, second.size(), "AU count");
        H264AccessUnitAssembler.AccessUnit au = second.get(0);
        assertEquals(90_000L, au.rtpTimestamp, "timestamp");
        assertEquals(120L, au.receivedNs, "receivedNs");
        if (!au.containsKeyFrame) throw new AssertionError("AU should contain IDR");
        assertBytes(concat(sei, idr), au.data, "AU payload");
    }

    private static void flushesPreviousTimestampBeforeStartingNextAccessUnit() {
        H264AccessUnitAssembler assembler = new H264AccessUnitAssembler();
        byte[] pFrame = annexB(1, 0x44);
        byte[] nextFrame = annexB(1, 0x55);

        assembler.addNal(pFrame, 90_000L, 100L, 1, false);
        List<H264AccessUnitAssembler.AccessUnit> flushed =
                assembler.addNal(nextFrame, 93_000L, 140L, 1, false);

        assertEquals(1, flushed.size(), "timestamp-change flush count");
        assertBytes(pFrame, flushed.get(0).data, "flushed payload");
        List<H264AccessUnitAssembler.AccessUnit> marker =
                assembler.addNal(annexB(1, 0x66), 93_000L, 160L, 1, true);
        assertEquals(1, marker.size(), "marker flush count");
        assertBytes(concat(nextFrame, annexB(1, 0x66)), marker.get(0).data, "current payload");
    }

    private static byte[] annexB(int nalType, int... payload) {
        byte[] data = new byte[payload.length + 5];
        data[0] = 0;
        data[1] = 0;
        data[2] = 0;
        data[3] = 1;
        data[4] = (byte) nalType;
        for (int i = 0; i < payload.length; i++) {
            data[i + 5] = (byte) payload[i];
        }
        return data;
    }

    private static byte[] concat(byte[]... arrays) {
        int length = 0;
        for (byte[] array : arrays) length += array.length;
        byte[] out = new byte[length];
        int offset = 0;
        for (byte[] array : arrays) {
            System.arraycopy(array, 0, out, offset, array.length);
            offset += array.length;
        }
        return out;
    }

    private static void assertBytes(byte[] expected, byte[] actual, String name) {
        if (expected.length != actual.length) {
            throw new AssertionError(name + " length expected=" + expected.length + " actual=" + actual.length);
        }
        for (int i = 0; i < expected.length; i++) {
            if (expected[i] != actual[i]) {
                throw new AssertionError(name + " byte[" + i + "] expected=" + expected[i] + " actual=" + actual[i]);
            }
        }
    }

    private static void assertEquals(long expected, long actual, String name) {
        if (expected != actual) {
            throw new AssertionError(name + " expected=" + expected + " actual=" + actual);
        }
    }
}
