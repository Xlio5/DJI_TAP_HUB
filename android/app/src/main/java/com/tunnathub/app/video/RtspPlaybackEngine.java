package com.tunnathub.app.video;

public enum RtspPlaybackEngine {
    UDP_SELF("udp_self", "自建UDP+PLI"),
    MEDIA3_UDP("media3_udp", "Media3 UDP探测");

    private final String prefValue;
    private final String label;

    RtspPlaybackEngine(String prefValue, String label) {
        this.prefValue = prefValue;
        this.label = label;
    }

    public String prefValue() {
        return prefValue;
    }

    public String label() {
        return label;
    }

    public static RtspPlaybackEngine fromPref(String value) {
        for (RtspPlaybackEngine engine : values()) {
            if (engine.prefValue.equals(value)) return engine;
        }
        return UDP_SELF;
    }
}
