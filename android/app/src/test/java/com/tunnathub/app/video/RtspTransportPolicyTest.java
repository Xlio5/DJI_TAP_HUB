package com.tunnathub.app.video;

public class RtspTransportPolicyTest {
    public static void main(String[] args) {
        if (RtspTransportPolicy.lowLatencyTransportType() != 2) {
            throw new AssertionError("low latency should use UDP transport");
        }
    }
}
