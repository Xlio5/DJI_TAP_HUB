package com.tunnathub.app.video;

public final class RtspUdpProbeParserTest {
    public static void main(String[] args) {
        parsesContentBaseAndVideoControlUrl();
        parsesUdpTransportPorts();
        detectsTcpInterleavedTransport();
    }

    private static void parsesContentBaseAndVideoControlUrl() {
        String describe =
            "RTSP/1.0 200 OK\r\n" +
            "CSeq: 2\r\n" +
            "Content-Base: rtsp://192.168.144.31:554/stream1/\r\n" +
            "Content-Type: application/sdp\r\n" +
            "\r\n" +
            "v=0\r\n" +
            "m=audio 0 RTP/AVP 0\r\n" +
            "a=control:trackID=1\r\n" +
            "m=video 0 RTP/AVP 96\r\n" +
            "a=rtpmap:96 H264/90000\r\n" +
            "a=control:trackID=0\r\n";

        String base = RtspUdpProbeParser.contentBase(describe, "rtsp://192.168.144.31:554/stream1");
        assertEquals("rtsp://192.168.144.31:554/stream1/", base, "content base");

        String control = RtspUdpProbeParser.firstVideoControl(describe);
        assertEquals("trackID=0", control, "video control");

        String setupUrl = RtspUdpProbeParser.resolveControlUrl(base, control);
        assertEquals("rtsp://192.168.144.31:554/stream1/trackID=0", setupUrl, "setup url");
    }

    private static void parsesUdpTransportPorts() {
        String setup =
            "RTSP/1.0 200 OK\r\n" +
            "CSeq: 3\r\n" +
            "Session: 12345678;timeout=60\r\n" +
            "Transport: RTP/AVP/UDP;unicast;client_port=50000-50001;server_port=6970-6971\r\n\r\n";

        RtspUdpProbeParser.Transport transport = RtspUdpProbeParser.transport(setup);
        if (transport == null) throw new AssertionError("transport should parse");
        if (transport.isTcpInterleaved()) throw new AssertionError("transport should be UDP");
        assertEquals(6970, transport.serverRtpPort(), "server RTP port");
        assertEquals(6971, transport.serverRtcpPort(), "server RTCP port");
    }

    private static void detectsTcpInterleavedTransport() {
        String setup =
            "RTSP/1.0 200 OK\r\n" +
            "CSeq: 3\r\n" +
            "Transport: RTP/AVP/TCP;unicast;interleaved=0-1\r\n\r\n";

        RtspUdpProbeParser.Transport transport = RtspUdpProbeParser.transport(setup);
        if (transport == null) throw new AssertionError("transport should parse");
        if (!transport.isTcpInterleaved()) throw new AssertionError("transport should detect TCP interleaved");
    }

    private static void assertEquals(Object expected, Object actual, String name) {
        if (!expected.equals(actual)) {
            throw new AssertionError(name + " expected=" + expected + " actual=" + actual);
        }
    }
}
