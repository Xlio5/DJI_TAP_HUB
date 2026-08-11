package com.tunnathub.app.video;

import java.net.DatagramPacket;

public final class RtspKeyFrameRequesterTest {
    public static void main(String[] args) {
        parsesRtpSsrc();
    }

    private static void parsesRtpSsrc() {
        byte[] data = new byte[] {
            (byte) 0x80, 96, 0x12, 0x34,
            0, 0, 0, 1,
            0x55, 0x66, 0x77, (byte) 0x88,
            0x65
        };
        DatagramPacket packet = new DatagramPacket(data, data.length);
        int ssrc = RtspKeyFrameRequester.parseRtpSsrc(packet);
        if (ssrc != 0x55667788) {
            throw new AssertionError("ssrc=0x" + Integer.toHexString(ssrc));
        }
    }
}
