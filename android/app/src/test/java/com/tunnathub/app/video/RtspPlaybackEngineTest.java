package com.tunnathub.app.video;

public final class RtspPlaybackEngineTest {
    public static void main(String[] args) {
        if (RtspPlaybackEngine.fromPref(null) != RtspPlaybackEngine.UDP_SELF) {
            throw new AssertionError("default engine should be UDP_SELF");
        }
        if (RtspPlaybackEngine.fromPref("low_latency") != RtspPlaybackEngine.UDP_SELF) {
            throw new AssertionError("legacy low_latency pref should migrate to UDP_SELF");
        }
        if (RtspPlaybackEngine.fromPref("media3_udp") != RtspPlaybackEngine.MEDIA3_UDP) {
            throw new AssertionError("media3_udp should select MEDIA3_UDP");
        }
        if (RtspPlaybackEngine.fromPref("qgc_software") != RtspPlaybackEngine.QGC_SOFTWARE) {
            throw new AssertionError("qgc_software should select QGC_SOFTWARE");
        }
        if (!"udp_self".equals(RtspPlaybackEngine.UDP_SELF.prefValue())) {
            throw new AssertionError("udp self pref value changed");
        }
        if (!RtspPlaybackEngine.QGC_SOFTWARE.usesSoftwareDecoder()) {
            throw new AssertionError("QGC style engine should force software decoder");
        }
    }
}
