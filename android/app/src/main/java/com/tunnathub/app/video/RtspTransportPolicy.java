package com.tunnathub.app.video;

import org.easydarwin.video.Client;

public final class RtspTransportPolicy {
    private RtspTransportPolicy() {
    }

    public static int lowLatencyTransportType() {
        return Client.TRANSTYPE_UDP;
    }
}
