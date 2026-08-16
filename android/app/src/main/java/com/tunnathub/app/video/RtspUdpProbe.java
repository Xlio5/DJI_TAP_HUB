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

public final class RtspUdpProbe {
    private RtspUdpProbe() {}

    public static Result run(String rtspUrl, int receiveSeconds) {
        return runInternal(rtspUrl, receiveSeconds, "normal", null, false);
    }

    public static Result runProtectedTun(String rtspUrl, int receiveSeconds) {
        return runInternal(rtspUrl, receiveSeconds, "tun_protected", "192.168.144.11", true);
    }

    private static Result runInternal(String rtspUrl, int receiveSeconds, String mode, String bindAddress, boolean protectUdp) {
        long startMs = System.currentTimeMillis();
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
            if (host == null || host.isBlank()) {
                return Result.error(rtspUrl, mode, "bad_url", "RTSP URL 缺少 host");
            }

            UdpPair udpPair = openUdpPair(bindAddress, protectUdp);
            rtp = udpPair.rtp;
            rtcp = udpPair.rtcp;
            rtp.setSoTimeout(500);
            rtcp.setSoTimeout(200);

            rtsp.connect(new InetSocketAddress(host, port), 3_000);
            rtsp.setSoTimeout(3_000);
            BufferedInputStream input = new BufferedInputStream(rtsp.getInputStream());
            BufferedWriter output = new BufferedWriter(new OutputStreamWriter(rtsp.getOutputStream(), StandardCharsets.UTF_8));

            int cseq = 1;
            String options = request(output, input, rtspUrl, "OPTIONS", cseq++, null, null);
            int optionsCode = RtspUdpProbeParser.statusCode(options);

            String describe = request(output, input, rtspUrl, "DESCRIBE", cseq++, "Accept: application/sdp\r\n", null);
            int describeCode = RtspUdpProbeParser.statusCode(describe);
            RtspUdpProbeParser.H264Sprop sprop = RtspUdpProbeParser.h264SpropParameterSets(describe);
            if (describeCode < 200 || describeCode >= 300) {
                return Result.error(rtspUrl, mode, "describe_" + describeCode, trimRtspStatus(describe));
            }

            String contentBase = RtspUdpProbeParser.contentBase(describe, rtspUrl);
            String control = RtspUdpProbeParser.firstVideoControl(describe);
            String setupUrl = RtspUdpProbeParser.resolveControlUrl(contentBase, control);
            String transportReq = "Transport: RTP/AVP/UDP;unicast;client_port="
                + udpPair.rtp.getLocalPort() + "-" + udpPair.rtcp.getLocalPort() + "\r\n";
            String setup = request(output, input, setupUrl, "SETUP", cseq++, transportReq, null);
            int setupCode = RtspUdpProbeParser.statusCode(setup);
            RtspUdpProbeParser.Transport transport = RtspUdpProbeParser.transport(setup);
            session = RtspUdpProbeParser.sessionId(setup);
            if (setupCode < 200 || setupCode >= 300) {
                return Result.error(rtspUrl, mode, "setup_" + setupCode, trimRtspStatus(setup))
                    .withRtsp(optionsCode, describeCode, setupCode, udpPair.rtp.getLocalPort(), udpPair.rtcp.getLocalPort(), transport);
            }
            if (transport != null && transport.isTcpInterleaved()) {
                return Result.error(rtspUrl, mode, "tcp_interleaved", "摄像头 SETUP 返回 TCP interleaved")
                    .withRtsp(optionsCode, describeCode, setupCode, udpPair.rtp.getLocalPort(), udpPair.rtcp.getLocalPort(), transport);
            }
            if (session == null || session.isBlank()) {
                return Result.error(rtspUrl, mode, "no_session", "SETUP 未返回 Session")
                    .withRtsp(optionsCode, describeCode, setupCode, udpPair.rtp.getLocalPort(), udpPair.rtcp.getLocalPort(), transport);
            }

            request(output, input, contentBase, "PLAY", cseq++, null, session);
            PacketStats stats = receiveRtp(rtp, receiveSeconds * 1000L);
            try {
                request(output, input, contentBase, "TEARDOWN", cseq, null, session);
            } catch (IOException ignored) {
                // 诊断结束时尽量释放 RTSP 会话即可。
            }
            return Result.ok(rtspUrl, mode, System.currentTimeMillis() - startMs, stats.packets, stats.bytes, stats.firstPacketMs)
                .withRtsp(optionsCode, describeCode, setupCode, udpPair.rtp.getLocalPort(), udpPair.rtcp.getLocalPort(), transport)
                .withPacketStats(stats.sequenceStats)
                .withSprop(sprop);
        } catch (Exception e) {
            return Result.error(rtspUrl, mode, e.getClass().getSimpleName(), e.getMessage());
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
        output.write("User-Agent: TUN_NAT_HUB_RtspUdpProbe\r\n");
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

    private static UdpPair openUdpPair(String bindAddress, boolean protectUdp) throws IOException {
        for (int i = 0; i < 24; i++) {
            DatagramSocket rtp = new DatagramSocket(null);
            rtp.setReuseAddress(true);
            rtp.bind(bindAddress == null ? new InetSocketAddress(0) : new InetSocketAddress(bindAddress, 0));
            int port = rtp.getLocalPort();
            if ((port & 1) != 0 || port >= 65535) {
                rtp.close();
                continue;
            }
            try {
                DatagramSocket rtcp = new DatagramSocket(null);
                rtcp.setReuseAddress(true);
                rtcp.bind(bindAddress == null ? new InetSocketAddress(port + 1) : new InetSocketAddress(bindAddress, port + 1));
                if (protectUdp) {
                    TunNatVpnService.Companion.protectSocket(rtp);
                    TunNatVpnService.Companion.protectSocket(rtcp);
                }
                return new UdpPair(rtp, rtcp);
            } catch (IOException e) {
                rtp.close();
            }
        }
        throw new IOException("无法分配连续 UDP RTP/RTCP 端口");
    }

    private static PacketStats receiveRtp(DatagramSocket rtp, long durationMs) throws IOException {
        long startMs = System.currentTimeMillis();
        long deadline = startMs + durationMs;
        byte[] buf = new byte[2048];
        DatagramPacket packet = new DatagramPacket(buf, buf.length);
        int packets = 0;
        long bytes = 0;
        long firstPacketMs = -1;
        RtpSequenceStats sequenceStats = new RtpSequenceStats();
        while (System.currentTimeMillis() < deadline) {
            try {
                rtp.receive(packet);
                if (firstPacketMs < 0) firstPacketMs = System.currentTimeMillis() - startMs;
                packets++;
                bytes += packet.getLength();
                int seq = parseRtpSequence(packet);
                if (seq >= 0) sequenceStats.observe(seq);
            } catch (java.net.SocketTimeoutException ignored) {
                // 短超时用于定期检查总测试时长。
            }
        }
        return new PacketStats(packets, bytes, firstPacketMs, sequenceStats);
    }

    private static int parseRtpSequence(DatagramPacket packet) {
        if (packet.getLength() < 4) return -1;
        byte[] data = packet.getData();
        int offset = packet.getOffset();
        int version = (data[offset] & 0xff) >> 6;
        if (version != 2) return -1;
        return ((data[offset + 2] & 0xff) << 8) | (data[offset + 3] & 0xff);
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

    private static final class PacketStats {
        final int packets;
        final long bytes;
        final long firstPacketMs;
        final RtpSequenceStats sequenceStats;

        PacketStats(int packets, long bytes, long firstPacketMs, RtpSequenceStats sequenceStats) {
            this.packets = packets;
            this.bytes = bytes;
            this.firstPacketMs = firstPacketMs;
            this.sequenceStats = sequenceStats;
        }
    }

    public static final class RtpSequenceStats {
        private int packets;
        private int lastSeq = -1;
        private int gaps;
        private int missingPackets;
        private int wraps;

        public void observe(int seq) {
            seq &= 0xffff;
            packets++;
            if (lastSeq >= 0) {
                int expected = (lastSeq + 1) & 0xffff;
                if (seq < lastSeq) wraps++;
                if (seq != expected) {
                    int diff = (seq - expected) & 0xffff;
                    if (diff > 0 && diff < 0x8000) {
                        gaps++;
                        missingPackets += diff;
                    }
                }
            }
            lastSeq = seq;
        }

        public int packets() { return packets; }
        public int gaps() { return gaps; }
        public int missingPackets() { return missingPackets; }
        public int wraps() { return wraps; }
    }

    public static final class Result {
        public final String rtspUrl;
        public final String mode;
        public final boolean ok;
        public final String errorCode;
        public final String errorMessage;
        public final long totalMs;
        public final int rtpPackets;
        public final long rtpBytes;
        public final long firstPacketMs;
        public final int optionsCode;
        public final int describeCode;
        public final int setupCode;
        public final int clientRtpPort;
        public final int clientRtcpPort;
        public final String transport;
        public final int serverRtpPort;
        public final int serverRtcpPort;
        public final int sequenceGaps;
        public final int sequenceMissingPackets;
        public final int sequenceWraps;
        public final int spsBytes;
        public final int ppsBytes;

        private Result(
            String rtspUrl,
            String mode,
            boolean ok,
            String errorCode,
            String errorMessage,
            long totalMs,
            int rtpPackets,
            long rtpBytes,
            long firstPacketMs,
            int optionsCode,
            int describeCode,
            int setupCode,
            int clientRtpPort,
            int clientRtcpPort,
            String transport,
            int serverRtpPort,
            int serverRtcpPort,
            int sequenceGaps,
            int sequenceMissingPackets,
            int sequenceWraps,
            int spsBytes,
            int ppsBytes
        ) {
            this.rtspUrl = rtspUrl;
            this.mode = mode;
            this.ok = ok;
            this.errorCode = errorCode;
            this.errorMessage = errorMessage;
            this.totalMs = totalMs;
            this.rtpPackets = rtpPackets;
            this.rtpBytes = rtpBytes;
            this.firstPacketMs = firstPacketMs;
            this.optionsCode = optionsCode;
            this.describeCode = describeCode;
            this.setupCode = setupCode;
            this.clientRtpPort = clientRtpPort;
            this.clientRtcpPort = clientRtcpPort;
            this.transport = transport;
            this.serverRtpPort = serverRtpPort;
            this.serverRtcpPort = serverRtcpPort;
            this.sequenceGaps = sequenceGaps;
            this.sequenceMissingPackets = sequenceMissingPackets;
            this.sequenceWraps = sequenceWraps;
            this.spsBytes = spsBytes;
            this.ppsBytes = ppsBytes;
        }

        static Result ok(String rtspUrl, String mode, long totalMs, int rtpPackets, long rtpBytes, long firstPacketMs) {
            return new Result(rtspUrl, mode, rtpPackets > 0, null, null, totalMs, rtpPackets, rtpBytes, firstPacketMs, -1, -1, -1, -1, -1, "", -1, -1, 0, 0, 0, 0, 0);
        }

        static Result error(String rtspUrl, String mode, String errorCode, String errorMessage) {
            return new Result(rtspUrl, mode, false, errorCode, errorMessage, 0, 0, 0, -1, -1, -1, -1, -1, -1, "", -1, -1, 0, 0, 0, 0, 0);
        }

        Result withRtsp(int optionsCode, int describeCode, int setupCode, int clientRtpPort, int clientRtcpPort, RtspUdpProbeParser.Transport parsedTransport) {
            String rawTransport = parsedTransport == null ? "" : parsedTransport.raw();
            int serverRtp = parsedTransport == null ? -1 : parsedTransport.serverRtpPort();
            int serverRtcp = parsedTransport == null ? -1 : parsedTransport.serverRtcpPort();
            return new Result(rtspUrl, mode, ok, errorCode, errorMessage, totalMs, rtpPackets, rtpBytes, firstPacketMs, optionsCode, describeCode, setupCode, clientRtpPort, clientRtcpPort, rawTransport, serverRtp, serverRtcp, sequenceGaps, sequenceMissingPackets, sequenceWraps, spsBytes, ppsBytes);
        }

        Result withPacketStats(RtpSequenceStats stats) {
            return new Result(rtspUrl, mode, ok, errorCode, errorMessage, totalMs, rtpPackets, rtpBytes, firstPacketMs, optionsCode, describeCode, setupCode, clientRtpPort, clientRtcpPort, transport, serverRtpPort, serverRtcpPort, stats.gaps(), stats.missingPackets(), stats.wraps(), spsBytes, ppsBytes);
        }

        Result withSprop(RtspUdpProbeParser.H264Sprop sprop) {
            int sps = sprop == null || sprop.sps == null ? 0 : sprop.sps.length;
            int pps = sprop == null || sprop.pps == null ? 0 : sprop.pps.length;
            return new Result(rtspUrl, mode, ok, errorCode, errorMessage, totalMs, rtpPackets, rtpBytes, firstPacketMs, optionsCode, describeCode, setupCode, clientRtpPort, clientRtcpPort, transport, serverRtpPort, serverRtcpPort, sequenceGaps, sequenceMissingPackets, sequenceWraps, sps, pps);
        }

        public String toDisplayString() {
            String base = "RTSP UDP[" + mode + "]: opt=" + optionsCode
                + " desc=" + describeCode
                + " setup=" + setupCode
                + " client=" + clientRtpPort + "-" + clientRtcpPort
                + " server=" + serverRtpPort + "-" + serverRtcpPort
                + " rtp=" + rtpPackets
                + " bytes=" + rtpBytes
                + " first=" + firstPacketMs + "ms"
                + " gap=" + sequenceGaps
                + " miss=" + sequenceMissingPackets
                + " wrap=" + sequenceWraps
                + " sps/pps=" + spsBytes + "/" + ppsBytes;
            if (transport != null && !transport.isBlank()) base += "\nTransport: " + transport;
            if (!ok) base += "\n结论: UDP RTP 未收到" + (errorCode == null ? "" : " (" + errorCode + ")") + (errorMessage == null ? "" : " " + errorMessage);
            else base += "\n结论: UDP RTP 可回流";
            return base;
        }
    }
}
