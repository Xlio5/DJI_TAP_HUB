package com.tunnathub.app.video;

import com.tunnathub.app.service.TunNatVpnService;

import java.io.BufferedInputStream;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.OutputStreamWriter;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.Locale;

public final class RtspKeyFrameRequester {
    private RtspKeyFrameRequester() {}

    public static Result request(String rtspUrl, int receiveMs) {
        boolean boundToVpn = TunNatVpnService.isVpnRunningForJava();
        Socket rtsp = new Socket();
        DatagramSocket rtp = null;
        DatagramSocket rtcp = null;
        String session = null;
        try {
            if (boundToVpn) TunNatVpnService.bindProcessToVpnNetwork();
            URI uri = URI.create(rtspUrl);
            String host = uri.getHost();
            int port = uri.getPort() > 0 ? uri.getPort() : 554;
            if (host == null || host.isBlank()) return Result.error("bad_url", "missing host");

            UdpPair udp = openUdpPair("10.0.0.2", true);
            rtp = udp.rtp;
            rtcp = udp.rtcp;
            rtp.setSoTimeout(300);

            rtsp.connect(new InetSocketAddress(host, port), 3_000);
            rtsp.setSoTimeout(3_000);
            BufferedInputStream input = new BufferedInputStream(rtsp.getInputStream());
            BufferedWriter output = new BufferedWriter(new OutputStreamWriter(rtsp.getOutputStream(), StandardCharsets.UTF_8));

            int cseq = 1;
            request(output, input, rtspUrl, "OPTIONS", cseq++, null, null);
            String describe = request(output, input, rtspUrl, "DESCRIBE", cseq++, "Accept: application/sdp\r\n", null);
            int describeCode = RtspUdpProbeParser.statusCode(describe);
            if (describeCode < 200 || describeCode >= 300) {
                return Result.error("describe_" + describeCode, trimRtspStatus(describe));
            }

            String contentBase = RtspUdpProbeParser.contentBase(describe, rtspUrl);
            String control = RtspUdpProbeParser.firstVideoControl(describe);
            String setupUrl = RtspUdpProbeParser.resolveControlUrl(contentBase, control);
            String transportReq = "Transport: RTP/AVP/UDP;unicast;client_port="
                + udp.rtp.getLocalPort() + "-" + udp.rtcp.getLocalPort() + "\r\n";
            String setup = request(output, input, setupUrl, "SETUP", cseq++, transportReq, null);
            int setupCode = RtspUdpProbeParser.statusCode(setup);
            RtspUdpProbeParser.Transport transport = RtspUdpProbeParser.transport(setup);
            session = RtspUdpProbeParser.sessionId(setup);
            if (setupCode < 200 || setupCode >= 300) {
                return Result.error("setup_" + setupCode, trimRtspStatus(setup));
            }
            if (transport == null || transport.serverRtcpPort() <= 0) {
                return Result.error("no_rtcp_port", "SETUP has no server RTCP port");
            }
            if (session == null || session.isBlank()) {
                return Result.error("no_session", "SETUP has no Session");
            }

            request(output, input, contentBase, "PLAY", cseq++, null, session);
            int mediaSsrc = receiveSsrc(rtp, receiveMs);
            if (mediaSsrc == 0) return Result.error("no_rtp_ssrc", "no RTP packet before feedback");

            int senderSsrc = 0x54554e48; // "TUNH"
            InetSocketAddress rtcpTarget = new InetSocketAddress(host, transport.serverRtcpPort());
            byte[] pli = RtcpFeedback.buildPli(senderSsrc, mediaSsrc);
            byte[] fir = RtcpFeedback.buildFir(senderSsrc, mediaSsrc, (int) (System.currentTimeMillis() & 0xff));
            rtcp.send(new DatagramPacket(pli, pli.length, rtcpTarget));
            rtcp.send(new DatagramPacket(fir, fir.length, rtcpTarget));

            try {
                request(output, input, contentBase, "TEARDOWN", cseq, null, session);
            } catch (IOException ignored) {
            }
            return Result.ok(mediaSsrc, transport.serverRtcpPort());
        } catch (Exception e) {
            return Result.error(e.getClass().getSimpleName(), e.getMessage());
        } finally {
            closeQuietly(rtp);
            closeQuietly(rtcp);
            try {
                rtsp.close();
            } catch (IOException ignored) {
            }
            if (boundToVpn) TunNatVpnService.clearProcessNetworkBinding();
        }
    }

    private static int receiveSsrc(DatagramSocket rtp, int receiveMs) throws IOException {
        long deadline = System.currentTimeMillis() + receiveMs;
        byte[] buf = new byte[2048];
        DatagramPacket packet = new DatagramPacket(buf, buf.length);
        while (System.currentTimeMillis() < deadline) {
            try {
                rtp.receive(packet);
                int ssrc = parseRtpSsrc(packet);
                if (ssrc != 0) return ssrc;
            } catch (java.net.SocketTimeoutException ignored) {
            }
        }
        return 0;
    }

    static int parseRtpSsrc(DatagramPacket packet) {
        if (packet.getLength() < 12) return 0;
        byte[] data = packet.getData();
        int offset = packet.getOffset();
        int version = (data[offset] & 0xff) >> 6;
        if (version != 2) return 0;
        return ((data[offset + 8] & 0xff) << 24)
            | ((data[offset + 9] & 0xff) << 16)
            | ((data[offset + 10] & 0xff) << 8)
            | (data[offset + 11] & 0xff);
    }

    private static UdpPair openUdpPair(String bindAddress, boolean protectUdp) throws IOException {
        for (int i = 0; i < 24; i++) {
            DatagramSocket rtp = new DatagramSocket(null);
            rtp.setReuseAddress(true);
            rtp.bind(new InetSocketAddress(bindAddress, 0));
            int port = rtp.getLocalPort();
            if ((port & 1) != 0 || port >= 65535) {
                rtp.close();
                continue;
            }
            try {
                DatagramSocket rtcp = new DatagramSocket(null);
                rtcp.setReuseAddress(true);
                rtcp.bind(new InetSocketAddress(bindAddress, port + 1));
                if (protectUdp) {
                    TunNatVpnService.Companion.protectSocket(rtp);
                    TunNatVpnService.Companion.protectSocket(rtcp);
                }
                return new UdpPair(rtp, rtcp);
            } catch (IOException e) {
                rtp.close();
            }
        }
        throw new IOException("cannot allocate RTP/RTCP UDP pair");
    }

    private static String request(
        BufferedWriter output,
        BufferedInputStream input,
        String url,
        String method,
        int cseq,
        String extraHeaders,
        String session
    ) throws IOException {
        output.write(method + " " + url + " RTSP/1.0\r\n");
        output.write("CSeq: " + cseq + "\r\n");
        output.write("User-Agent: TUN_NAT_HUB_KeyFrameRequester\r\n");
        if (session != null && !session.isBlank()) output.write("Session: " + session + "\r\n");
        if (extraHeaders != null) output.write(extraHeaders);
        output.write("\r\n");
        output.flush();
        return readResponse(input);
    }

    private static String readResponse(BufferedInputStream input) throws IOException {
        StringBuilder header = new StringBuilder();
        int matched = 0;
        while (true) {
            int b = input.read();
            if (b < 0) break;
            header.append((char) b);
            matched = matchEnd(matched, b);
            if (matched == 4) break;
            if (header.length() > 16_384) throw new IOException("RTSP header too large");
        }
        int contentLength = 0;
        String headerText = header.toString();
        for (String line : headerText.split("\\r?\\n")) {
            int colon = line.indexOf(':');
            if (colon <= 0) continue;
            if ("content-length".equals(line.substring(0, colon).trim().toLowerCase(Locale.US))) {
                contentLength = Integer.parseInt(line.substring(colon + 1).trim());
            }
        }
        byte[] body = new byte[contentLength];
        int offset = 0;
        while (offset < contentLength) {
            int n = input.read(body, offset, contentLength - offset);
            if (n < 0) break;
            offset += n;
        }
        return headerText + new String(body, 0, offset, StandardCharsets.UTF_8);
    }

    private static int matchEnd(int matched, int b) {
        byte[] end = new byte[] {'\r', '\n', '\r', '\n'};
        if (b == end[matched]) return matched + 1;
        return b == '\r' ? 1 : 0;
    }

    private static String trimRtspStatus(String response) {
        int end = response.indexOf("\r\n");
        if (end < 0) end = response.indexOf('\n');
        return end < 0 ? response : response.substring(0, end);
    }

    private static void closeQuietly(DatagramSocket socket) {
        if (socket != null) socket.close();
    }

    private static final class UdpPair {
        final DatagramSocket rtp;
        final DatagramSocket rtcp;

        UdpPair(DatagramSocket rtp, DatagramSocket rtcp) {
            this.rtp = rtp;
            this.rtcp = rtcp;
        }
    }

    public static final class Result {
        public final boolean ok;
        public final String errorCode;
        public final String errorMessage;
        public final int mediaSsrc;
        public final int serverRtcpPort;

        private Result(boolean ok, String errorCode, String errorMessage, int mediaSsrc, int serverRtcpPort) {
            this.ok = ok;
            this.errorCode = errorCode;
            this.errorMessage = errorMessage;
            this.mediaSsrc = mediaSsrc;
            this.serverRtcpPort = serverRtcpPort;
        }

        static Result ok(int mediaSsrc, int serverRtcpPort) {
            return new Result(true, null, null, mediaSsrc, serverRtcpPort);
        }

        static Result error(String errorCode, String errorMessage) {
            return new Result(false, errorCode, errorMessage, 0, -1);
        }

        public String toDisplayString() {
            if (ok) {
                return "RTCP PLI/FIR sent ssrc=0x" + Integer.toHexString(mediaSsrc)
                    + " rtcp=" + serverRtcpPort;
            }
            return "RTCP PLI/FIR failed " + errorCode
                + (errorMessage == null ? "" : " " + errorMessage);
        }
    }
}
