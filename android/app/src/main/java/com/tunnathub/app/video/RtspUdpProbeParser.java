package com.tunnathub.app.video;

import java.net.URI;
import java.util.Base64;
import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public final class RtspUdpProbeParser {
    private static final Pattern HEADER_PATTERN = Pattern.compile("(?im)^%s\\s*:\\s*(.+?)\\s*$");

    private RtspUdpProbeParser() {}

    public static String contentBase(String response, String fallbackUrl) {
        String base = header(response, "Content-Base");
        if (base == null) base = header(response, "Content-Location");
        return base == null || base.isBlank() ? fallbackUrl : base.trim();
    }

    public static String firstVideoControl(String response) {
        String body = body(response);
        String[] lines = body.split("\\r?\\n");
        boolean inVideo = false;
        String sessionControl = null;
        for (String raw : lines) {
            String line = raw.trim();
            if (line.startsWith("m=")) {
                inVideo = line.toLowerCase(Locale.US).startsWith("m=video");
                continue;
            }
            if (!line.startsWith("a=control:")) continue;
            String control = line.substring("a=control:".length()).trim();
            if (inVideo) return control;
            if ("*".equals(control)) sessionControl = control;
        }
        return sessionControl;
    }

    public static String resolveControlUrl(String baseUrl, String control) {
        if (control == null || control.isBlank() || "*".equals(control)) return baseUrl;
        if (control.startsWith("rtsp://") || control.startsWith("rtsps://")) return control;
        try {
            String normalizedBase = baseUrl.endsWith("/") ? baseUrl : baseUrl + "/";
            return URI.create(normalizedBase).resolve(control).toString();
        } catch (IllegalArgumentException e) {
            return baseUrl.endsWith("/") ? baseUrl + control : baseUrl + "/" + control;
        }
    }

    public static Transport transport(String response) {
        String value = header(response, "Transport");
        if (value == null) return null;
        boolean tcp = value.toUpperCase(Locale.US).contains("RTP/AVP/TCP")
            || value.toLowerCase(Locale.US).contains("interleaved=");
        int[] serverPorts = parsePortPair(value, "server_port");
        int[] clientPorts = parsePortPair(value, "client_port");
        return new Transport(value.trim(), tcp, clientPorts[0], clientPorts[1], serverPorts[0], serverPorts[1]);
    }

    public static String sessionId(String response) {
        String session = header(response, "Session");
        if (session == null) return null;
        int semi = session.indexOf(';');
        return (semi >= 0 ? session.substring(0, semi) : session).trim();
    }

    public static H264Sprop h264SpropParameterSets(String response) {
        String body = body(response);
        Matcher m = Pattern.compile("(?im)^a=fmtp:\\d+\\s+(.+)$").matcher(body);
        while (m.find()) {
            Matcher sprop = Pattern.compile("(?i)(?:^|;)\\s*sprop-parameter-sets\\s*=\\s*([^;\\r\\n]+)")
                .matcher(m.group(1));
            if (!sprop.find()) continue;
            String[] parts = sprop.group(1).split(",");
            if (parts.length < 2) return null;
            try {
                return new H264Sprop(
                    Base64.getDecoder().decode(parts[0].trim()),
                    Base64.getDecoder().decode(parts[1].trim())
                );
            } catch (IllegalArgumentException ignored) {
                return null;
            }
        }
        return null;
    }

    public static int statusCode(String response) {
        Matcher m = Pattern.compile("(?m)^RTSP/\\d\\.\\d\\s+(\\d{3})").matcher(response);
        return m.find() ? Integer.parseInt(m.group(1)) : -1;
    }

    private static String header(String response, String name) {
        Matcher m = Pattern.compile(String.format(HEADER_PATTERN.pattern(), Pattern.quote(name))).matcher(response);
        return m.find() ? m.group(1).trim() : null;
    }

    private static String body(String response) {
        int idx = response.indexOf("\r\n\r\n");
        int skip = 4;
        if (idx < 0) {
            idx = response.indexOf("\n\n");
            skip = 2;
        }
        return idx < 0 ? "" : response.substring(idx + skip);
    }

    private static int[] parsePortPair(String value, String key) {
        Matcher m = Pattern.compile("(?i)(?:^|;)\\s*" + key + "\\s*=\\s*(\\d+)(?:\\s*-\\s*(\\d+))?").matcher(value);
        if (!m.find()) return new int[] {-1, -1};
        int first = Integer.parseInt(m.group(1));
        int second = m.group(2) == null ? -1 : Integer.parseInt(m.group(2));
        return new int[] {first, second};
    }

    public static final class Transport {
        private final String raw;
        private final boolean tcpInterleaved;
        private final int clientRtpPort;
        private final int clientRtcpPort;
        private final int serverRtpPort;
        private final int serverRtcpPort;

        Transport(String raw, boolean tcpInterleaved, int clientRtpPort, int clientRtcpPort, int serverRtpPort, int serverRtcpPort) {
            this.raw = raw;
            this.tcpInterleaved = tcpInterleaved;
            this.clientRtpPort = clientRtpPort;
            this.clientRtcpPort = clientRtcpPort;
            this.serverRtpPort = serverRtpPort;
            this.serverRtcpPort = serverRtcpPort;
        }

        public String raw() { return raw; }
        public boolean isTcpInterleaved() { return tcpInterleaved; }
        public int clientRtpPort() { return clientRtpPort; }
        public int clientRtcpPort() { return clientRtcpPort; }
        public int serverRtpPort() { return serverRtpPort; }
        public int serverRtcpPort() { return serverRtcpPort; }
    }

    public static final class H264Sprop {
        public final byte[] sps;
        public final byte[] pps;

        H264Sprop(byte[] sps, byte[] pps) {
            this.sps = sps;
            this.pps = pps;
        }
    }
}
