package com.tunnathub.app.video;

public final class RtspPlaybackEngineTest {
    public static void main(String[] args) {
        if (RtspPlaybackEngine.fromPref(null) != RtspPlaybackEngine.LOW_LATENCY) {
            throw new AssertionError("default engine should be LOW_LATENCY");
        }
        if (RtspPlaybackEngine.fromPref("media3_udp") != RtspPlaybackEngine.MEDIA3_UDP) {
            throw new AssertionError("media3_udp should select MEDIA3_UDP");
        }
        if (!"low_latency".equals(RtspPlaybackEngine.LOW_LATENCY.prefValue())) {
            throw new AssertionError("low latency pref value changed");
        }
    }
}
