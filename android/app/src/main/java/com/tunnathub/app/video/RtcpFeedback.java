package com.tunnathub.app.video;

public final class RtcpFeedback {
    private static final int PT_PSFB = 206;

    private RtcpFeedback() {}

    public static byte[] buildPli(int senderSsrc, int mediaSsrc) {
        byte[] out = new byte[12];
        out[0] = (byte) 0x81; // V=2, FMT=1 (PLI)
        out[1] = (byte) PT_PSFB;
        writeShort(out, 2, 2);
        writeInt(out, 4, senderSsrc);
        writeInt(out, 8, mediaSsrc);
        return out;
    }

    public static byte[] buildFir(int senderSsrc, int mediaSsrc, int seqNr) {
        byte[] out = new byte[20];
        out[0] = (byte) 0x84; // V=2, FMT=4 (FIR)
        out[1] = (byte) PT_PSFB;
        writeShort(out, 2, 4);
        writeInt(out, 4, senderSsrc);
        writeInt(out, 8, 0);
        writeInt(out, 12, mediaSsrc);
        out[16] = (byte) seqNr;
        return out;
    }

    private static void writeShort(byte[] out, int offset, int value) {
        out[offset] = (byte) (value >> 8);
        out[offset + 1] = (byte) value;
    }

    private static void writeInt(byte[] out, int offset, int value) {
        out[offset] = (byte) (value >> 24);
        out[offset + 1] = (byte) (value >> 16);
        out[offset + 2] = (byte) (value >> 8);
        out[offset + 3] = (byte) value;
    }
}
