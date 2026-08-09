package com.tunnathub.app.video;

public enum RtspPlaybackEngine {
    UDP_SELF("udp_self", "自建UDP+硬解", false),
    QGC_SOFTWARE("qgc_software", "QGC风格软解", true),
    MEDIA3_UDP("media3_udp", "Media3 UDP探测", false);

    private final String prefValue;
    private final String label;
    private final boolean softwareDecoder;

    RtspPlaybackEngine(String prefValue, String label, boolean softwareDecoder) {
        this.prefValue = prefValue;
        this.label = label;
        this.softwareDecoder = softwareDecoder;
    }

    public String prefValue() {
        return prefValue;
    }

    public String label() {
        return label;
    }

    public boolean usesSoftwareDecoder() {
        return softwareDecoder;
    }

    public static RtspPlaybackEngine fromPref(String value) {
        for (RtspPlaybackEngine engine : values()) {
            if (engine.prefValue.equals(value)) return engine;
        }
        return UDP_SELF;
    }
}
