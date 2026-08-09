package com.tunnathub.app.video;

import android.content.Context;
import android.media.MediaCodec;
import android.media.MediaCodecInfo;
import android.media.MediaFormat;
import android.util.Log;
import android.view.Surface;

import com.tunnathub.app.service.TunNatVpnService;

import org.easydarwin.video.BenchmarkStats;
import org.easydarwin.video.LowLatencyRtspPlayer;
import org.easydarwin.video.RtspPlayerSession;

import java.io.BufferedInputStream;
import java.io.BufferedWriter;
import java.io.IOException;
import java.io.OutputStreamWriter;
import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetSocketAddress;
import java.net.Socket;
import java.net.URI;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.util.ArrayDeque;
import java.util.Arrays;
import java.util.Locale;
import java.util.Map;
import java.util.Queue;
import java.util.TreeMap;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.TimeUnit;

/**
 * 自建 RTSP UDP 会话播放器：绕开 EasyRTSPClient 黑盒，全链路可控。
 *
 * <p>解决"有流量无画面"（摄像头不主动发关键帧）：
 * <ul>
 *   <li>自建 RTSP 握手，client_port 强制 ≥ 10000（V3s DNAT 只覆盖 10000:65535）；</li>
 *   <li>自建 RTP 接收 + H264 分片重组（FU-A/STAP-A/单 NAL），容忍乱序；</li>
 *   <li>等不到关键帧时主动向 server RTCP 端口发 PLI/FIR 逼摄像头产 IDR
 *       （参考 Moonlight"主动请求 IDR"而非盲重启）；</li>
 *   <li>重组帧喂 MediaCodec 低延迟解码（复用 LowLatencyRtspPlayer 解码逻辑）。</li>
 * </ul>
 */
public final class UdpRtspPlayer implements RtspPlayerSession {
    public interface Callback {
        void onVideoDisplayed(String codecName);
        void onVideoSize(int width, int height);
        void onTimeout();
        void onUnsupportedVideo();
        void onError(String message, Throwable error);
        default void onStats(BenchmarkStats.Snapshot snapshot) {}
        default void onWaitingKeyFrame(long elapsedMs, int pliSent) {}
        default void onRtpDiag(String message) {}
    }

    private static final String TAG = "UdpRtspPlayer";
    private static final String VPN_IP = "10.0.0.2";          // 手机 TUN 地址
    private static final int MIN_CLIENT_PORT = 10000;         // V3s DNAT 10000:65535
    private static final long KEY_FRAME_PLI_INTERVAL_NS = 1_500_000_000L;
    private static final long WAIT_KEY_FRAME_TIMEOUT_NS = 10_000_000_000L;
    private static final int MAX_PLI_BEFORE_RESTART = 6;
    private static final int REORDER_WINDOW = 256;         // RTP 乱序容忍窗口（覆盖完整 IDR 分片 ~110 个）

    private final Context context;
    private final Surface surface;
    private final Callback callback;

    private volatile boolean running;
    private Thread rtpThread;
    private Thread decoderThread;
    private Thread keepAliveThread;

    private DatagramSocket rtpSocket;
    private DatagramSocket rtcpSocket;
    private Socket rtspSocket;
    private volatile boolean processBoundToVpn;

    // RTSP 会话信息
    private volatile String lastUrl;
    private volatile String sessionId;
    private volatile String rtspHost;
    private volatile int serverRtcpPort;
    private volatile int mediaSsrc;
    private int rtspControlCseq = 1;
    private final Object rtspLock = new Object();

    // RTP 重组状态（同一 timestamp 为一帧，FU-A 聚合）
    private final TreeMap<Integer, RtpPacket> reorder = new TreeMap<>();
    private int lastFlushedSeq = -1;
    private int lastRtpTimestamp = -1;
    private final byte[] fuAccum = new byte[512 * 1024];
    private int fuAccumLen;
    private int fuNalType = -1;
    private int fuNextSeq = -1;

    // SPS/PPS 缓存（configure 时作为 csd）
    private byte[] cachedSps;
    private byte[] cachedPps;

    // 解码状态
    private MediaCodec codec;
    private String codecName;
    private long firstStampUs;
    private boolean decoded;
    private final Queue<Long> inputTimesNs = new ArrayDeque<>();
    private final ArrayBlockingQueue<FrameSample> frameQueue = new ArrayBlockingQueue<>(4);
    private int width;
    private int height;

    // 关键帧等待状态
    private boolean waitingKeyFrame = true;
    private int pliSent;
    private long lastPliNs;
    private long keyFrameWaitStartNs;
    private volatile boolean restartInProgress;
    private long diagRtpPkts;
    private long diagIdrStartPkts;
    private long diagIdrCompletePkts;
    private long diagLastLogNs;
    private int diagSeqGaps;
    private int diagPrevSeq = -1;
    private long diagFuDiscards;
    private long diagReorderFlush;

    private static final class FrameSample {
        final byte[] data;
        final long rtpTimestamp;
        final long receivedNs;

        FrameSample(byte[] data, long rtpTimestamp, long receivedNs) {
            this.data = data;
            this.rtpTimestamp = rtpTimestamp;
            this.receivedNs = receivedNs;
        }
    }

    public UdpRtspPlayer(Context context, Surface surface, Callback callback) {
        this.context = context.getApplicationContext();
        this.surface = surface;
        this.callback = callback;
    }

    public synchronized int start(String url) {
        if (running) stop();
        running = true;
        lastUrl = url;
        waitingKeyFrame = true;
        pliSent = 0;
        lastPliNs = 0;
        keyFrameWaitStartNs = System.nanoTime();
        cachedSps = null;
        cachedPps = null;
        firstStampUs = 0;
        decoded = false;
        resetReassembler();
        frameQueue.clear();

        processBoundToVpn = TunNatVpnService.bindProcessToVpnNetwork();

        // 握手含网络 IO（connect/bind），放到后台线程避免 NetworkOnMainThreadException。
        // 异步成功后由 sessionThread 自己起 RTP/解码/保活线程。
        Thread sessionThread = new Thread(() -> {
            synchronized (UdpRtspPlayer.this) {
                if (!running) return;
                boolean opened = openSession(url);
                if (!opened) {
                    running = false;
                    if (processBoundToVpn) {
                        TunNatVpnService.clearProcessNetworkBinding();
                        processBoundToVpn = false;
                    }
                    return;
                }
                rtpThread = new Thread(this::rtpLoop, "UDP_RTP_RECV");
                rtpThread.start();
                decoderThread = new Thread(this::decodeLoop, "UDP_DECODER");
                decoderThread.start();
                keepAliveThread = new Thread(this::keepAliveLoop, "UDP_RTSP_KEEPALIVE");
                keepAliveThread.start();
            }
        }, "UDP_RTSP_SESSION");
        sessionThread.start();
        return 0;
    }

    @Override
    public synchronized void stop() {
        running = false;
        frameQueue.clear();

        Thread rt = rtpThread;
        rtpThread = null;
        if (rt != null) {
            rt.interrupt();
            try {
                rt.join(800);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }
        Thread dt = decoderThread;
        decoderThread = null;
        if (dt != null) {
            dt.interrupt();
            try {
                dt.join(800);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }
        Thread kt = keepAliveThread;
        keepAliveThread = null;
        if (kt != null) {
            kt.interrupt();
            try {
                kt.join(500);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }
        releaseCodec();
        closeSockets();
        if (processBoundToVpn) {
            TunNatVpnService.clearProcessNetworkBinding();
            processBoundToVpn = false;
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // RTSP 握手
    // ═══════════════════════════════════════════════════════════════

    private boolean openSession(String url) {
        try {
            URI uri = URI.create(url);
            String host = uri.getHost();
            int port = uri.getPort() > 0 ? uri.getPort() : 554;
            if (host == null || host.isBlank()) {
                callback.onError("bad_url", null);
                return false;
            }
            rtspHost = host;

            // 关键：client_port ≥ 10000，V3s DNAT 才覆盖
            int[] ports = allocateUdpPair();
            if (ports == null) {
                callback.onError("no_udp_ports", null);
                return false;
            }
            rtpSocket = new DatagramSocket(null);
            rtpSocket.setReuseAddress(true);
            rtpSocket.bind(new InetSocketAddress(VPN_IP, ports[0]));
            // 注意：不要 protectSocket。RTP 从 V3s DNAT 到 10.0.0.2 后经 tun0 回环给本机，
            // socket 必须留在 VPN 网络内才能收到；protect 会让它绕过 VPN 收不到。
            rtcpSocket = new DatagramSocket(null);
            rtcpSocket.setReuseAddress(true);
            // RTCP 发送 socket 绑通配地址而非 10.0.0.2：绑具体 VPN 地址 + VpnService 时，
            // 出方向包（PLI/FIR 到摄像头）会被路由静默丢弃；通配地址让路由决定源地址。
            rtcpSocket.bind(new InetSocketAddress(ports[1]));
            rtpSocket.setSoTimeout(100);

            rtspSocket = new Socket();
            rtspSocket.connect(new InetSocketAddress(host, port), 3_000);
            rtspSocket.setSoTimeout(3_000);
            BufferedInputStream input = new BufferedInputStream(rtspSocket.getInputStream());
            BufferedWriter output = new BufferedWriter(new OutputStreamWriter(rtspSocket.getOutputStream(), StandardCharsets.UTF_8));

            String options = request(input, output, url, "OPTIONS", null, null);
            callback.onRtpDiag("OPTIONS " + RtspUdpProbeParser.statusCode(options));

            String describe = request(input, output, url, "DESCRIBE", "Accept: application/sdp\r\n", null);
            int describeCode = RtspUdpProbeParser.statusCode(describe);
            if (describeCode < 200 || describeCode >= 300) {
                callback.onError("describe_" + describeCode, null);
                return false;
            }
            String contentBase = RtspUdpProbeParser.contentBase(describe, url);
            String control = RtspUdpProbeParser.firstVideoControl(describe);
            String setupUrl = RtspUdpProbeParser.resolveControlUrl(contentBase, control);
            String transportReq = "Transport: RTP/AVP/UDP;unicast;client_port="
                    + ports[0] + "-" + ports[1] + "\r\n";
            String setup = request(input, output, setupUrl, "SETUP", transportReq, null);
            int setupCode = RtspUdpProbeParser.statusCode(setup);
            RtspUdpProbeParser.Transport transport = RtspUdpProbeParser.transport(setup);
            sessionId = RtspUdpProbeParser.sessionId(setup);
            callback.onRtpDiag("SETUP " + setupCode + " " + (transport == null ? "" : transport.raw()));
            if (setupCode < 200 || setupCode >= 300 || transport == null || transport.isTcpInterleaved()) {
                callback.onError("setup_" + setupCode, null);
                return false;
            }
            serverRtcpPort = transport.serverRtcpPort();

            String play = request(input, output, contentBase, "PLAY", null, sessionId);
            int playCode = RtspUdpProbeParser.statusCode(play);
            callback.onRtpDiag("PLAY " + playCode);
            if (playCode < 200 || playCode >= 300) {
                callback.onError("play_" + playCode, null);
                return false;
            }
            callback.onRtpDiag("client_port=" + ports[0] + "-" + ports[1]
                    + " server_rtcp=" + serverRtcpPort + " session=" + sessionId);
            return true;
        } catch (IOException e) {
            callback.onError(e.getClass().getSimpleName(), e);
            return false;
        }
    }

    /** 分配 ≥10000 的连续偶数端口对（RTP, RTCP=RTP+1）。 */
    private int[] allocateUdpPair() {
        int base = MIN_CLIENT_PORT + (int) (Math.abs(System.nanoTime()) % 10000);
        if ((base & 1) != 0) base++;
        for (int i = 0; i < 200; i++) {
            int port = base + i * 2;
            if (port > 65534) return null;
            DatagramSocket s1 = null, s2 = null;
            try {
                s1 = new DatagramSocket(null);
                s1.setReuseAddress(true);
                s1.bind(new InetSocketAddress(VPN_IP, port));
                s2 = new DatagramSocket(null);
                s2.setReuseAddress(true);
                s2.bind(new InetSocketAddress(VPN_IP, port + 1));
                s1.close();
                s2.close();
                return new int[] {port, port + 1};
            } catch (IOException ignored) {
                if (s1 != null) s1.close();
                if (s2 != null) s2.close();
            }
        }
        return null;
    }

    private String request(BufferedInputStream input, BufferedWriter output, String url,
                           String method, String extraHeaders, String session) throws IOException {
        int cseq;
        synchronized (rtspLock) {
            cseq = rtspControlCseq++;
        }
        output.write(method + " " + url + " RTSP/1.0\r\n");
        output.write("CSeq: " + cseq + "\r\n");
        output.write("User-Agent: TUN_NAT_HUB_UdpRtspPlayer\r\n");
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

    // ═══════════════════════════════════════════════════════════════
    // RTP 接收 + 重组
    // ═══════════════════════════════════════════════════════════════

    private void rtpLoop() {
        byte[] buf = new byte[1500];
        DatagramPacket packet = new DatagramPacket(buf, buf.length);
        while (running) {
            DatagramSocket s = rtpSocket;
            if (s == null) break;
            try {
                s.receive(packet);
            } catch (java.net.SocketTimeoutException ignored) {
                maybeSendPli(System.nanoTime());
                continue;
            } catch (IOException e) {
                if (!running) break;
                // restartSession 会关闭旧 socket 并重开，短暂重试
                try {
                    Thread.sleep(50);
                } catch (InterruptedException ie) {
                    Thread.currentThread().interrupt();
                    break;
                }
                continue;
            }
            if (packet.getLength() < 12) continue;
            long receivedNs = System.nanoTime();
            RtpPacket rtp = parseRtp(packet.getData(), packet.getOffset(), packet.getLength());
            if (rtp == null) continue;
            if (mediaSsrc == 0) mediaSsrc = rtp.ssrc;
            if (mediaSsrc != rtp.ssrc) continue;
            diagRtpPkts++;
            // 诊断：seq 跳变统计（隧道丢包/乱序）
            if (diagPrevSeq >= 0) {
                int diff = (rtp.seq - diagPrevSeq) & 0xFFFF;
                if (diff != 1 && diff < 0xFF00) diagSeqGaps++;
            }
            diagPrevSeq = rtp.seq;
            // 诊断：统计 IDR 分片（FU-A start 类型 5）
            if (rtp.payload != null && rtp.payload.length >= 2
                    && (rtp.payload[0] & 0x1f) == 28 && (rtp.payload[1] & 0x80) != 0
                    && (rtp.payload[1] & 0x1f) == 5) {
                diagIdrStartPkts++;
            }
            long nowNs = System.nanoTime();
            if (nowNs - diagLastLogNs >= 3_000_000_000L) {
                diagLastLogNs = nowNs;
                Log.i(TAG, "diag rtp=" + diagRtpPkts
                        + " idrStart=" + diagIdrStartPkts
                        + " idrDone=" + diagIdrCompletePkts
                        + " gaps=" + diagSeqGaps
                        + " fuDisc=" + diagFuDiscards
                        + " reorderFlush=" + diagReorderFlush
                        + " waitingKey=" + waitingKeyFrame);
            }
            offerRtp(rtp);
            maybeSendPli(receivedNs);
        }
    }

    /** 收 RTP 进乱序缓冲，凑齐连续 seq 后按序出给重组器。 */
    private void offerRtp(RtpPacket rtp) {
        // 首次收到包：从该包的 seq 开始期望连续，避免 lastFlushedSeq=-1 卡死（首包 seq 通常非 0）
        if (lastFlushedSeq < 0) {
            lastFlushedSeq = rtp.seq - 1;
        }
        // 如果来了个明显更早的包（乱序延迟过大），以它为基准重新对齐，避免永久阻塞
        if (rtp.seq < lastFlushedSeq) {
            lastFlushedSeq = rtp.seq - 1;
        }
        reorder.put(rtp.seq, rtp);
        while (reorder.containsKey(lastFlushedSeq + 1)) {
            RtpPacket next = reorder.remove(lastFlushedSeq + 1);
            lastFlushedSeq = next.seq;
            assembleRtp(next);
        }
        // 缓冲超窗：说明中间有丢包（seq 空洞），跳过空洞继续——把已到达的包按序输出
        if (reorder.size() > REORDER_WINDOW) {
            diagReorderFlush++;
            int lowest = reorder.firstKey();
            while (!reorder.isEmpty() && reorder.firstKey() <= lastFlushedSeq) {
                reorder.remove(reorder.firstKey());
            }
            if (!reorder.isEmpty()) {
                int nextLowest = reorder.firstKey();
                // 跳过从 lastFlushedSeq+1 到 nextLowest-1 的空洞，从 nextLowest 重新连续
                lastFlushedSeq = nextLowest - 1;
            }
        }
    }

    private void assembleRtp(RtpPacket rtp) {
        // 同一 timestamp 的多个 RTP 包属于同一帧；重组按 timestamp 分组，
        // 但 FU-A 聚合本身跨包按 seq 拼接，因此 timestamp 变化仅作为统计参考。
        if (rtp.payload == null || rtp.payload.length == 0) return;

        int nalType = rtp.payload[0] & 0x1f;
        if (nalType == 28) {          // FU-A 分片
            if (rtp.payload.length < 2) return;
            int fuHeader = rtp.payload[1] & 0xff;
            int fuNal = fuHeader & 0x1f;
            boolean start = (fuHeader & 0x80) != 0;
            boolean end = (fuHeader & 0x40) != 0;

            if (start) {
                // 新分片开始
                fuNalType = fuNal;
                fuNextSeq = rtp.seq + 1;
                fuAccumLen = 0;
                // 重建 Annex-B：start code + NAL header（复用 FU indicator 的高位 NRI）
                fuAccum[0] = 0;
                fuAccum[1] = 0;
                fuAccum[2] = 0;
                fuAccum[3] = 1;
                fuAccum[4] = (byte) ((rtp.payload[0] & 0xe0) | fuNal);
                fuAccumLen = 5;
                int len = rtp.payload.length - 2;
                System.arraycopy(rtp.payload, 2, fuAccum, fuAccumLen, len);
                fuAccumLen += len;
            } else {
                // 非起始分片：必须严格接续上一个分片，否则丢弃整个聚合（丢包）
                if (fuNalType != fuNal || rtp.seq != fuNextSeq) {
                    diagFuDiscards++;
                    fuNalType = -1;
                    fuAccumLen = 0;
                    return;
                }
                // 续片是纯 NAL 数据流：直接拼接，不插入 start code / NAL header
                int len = rtp.payload.length - 2;
                if (fuAccumLen + len > fuAccum.length) {
                    fuNalType = -1;
                    fuAccumLen = 0;
                    return;
                }
                System.arraycopy(rtp.payload, 2, fuAccum, fuAccumLen, len);
                fuAccumLen += len;
                fuNextSeq = rtp.seq + 1;
            }
            if (end) {
                byte[] frame = Arrays.copyOf(fuAccum, fuAccumLen);
                fuNalType = -1;
                fuAccumLen = 0;
                if (fuNal == 5) diagIdrCompletePkts++;
                emitFrame(frame, rtp.timestamp, System.nanoTime(), fuNal);
            }
        } else if (nalType == 24) {   // STAP-A 聚合
            int i = 1;
            while (i + 2 <= rtp.payload.length) {
                int nalLen = ((rtp.payload[i] & 0xff) << 8) | (rtp.payload[i + 1] & 0xff);
                i += 2;
                if (i + nalLen > rtp.payload.length) break;
                int n = rtp.payload[i] & 0x1f;
                byte[] nal = new byte[nalLen + 4];
                nal[0] = 0; nal[1] = 0; nal[2] = 0; nal[3] = 1;
                System.arraycopy(rtp.payload, i, nal, 4, nalLen);
                emitFrame(nal, rtp.timestamp, System.nanoTime(), n);
                i += nalLen;
            }
        } else {                       // 单 NAL
            byte[] nal = new byte[rtp.payload.length + 4];
            nal[0] = 0; nal[1] = 0; nal[2] = 0; nal[3] = 1;
            System.arraycopy(rtp.payload, 0, nal, 4, rtp.payload.length);
            emitFrame(nal, rtp.timestamp, System.nanoTime(), nalType);
        }
    }

    /** 输出一帧到解码队列；等关键帧时只在完整 IDR（nal=5）时解除等待。 */
    private void emitFrame(byte[] data, long rtpTimestamp, long receivedNs, int nalInfo) {
        if (!running) return;
        // 缓存 SPS/PPS 作为 csd
        if (nalInfo == 7) { cachedSps = data; return; }  // SPS 仅作 csd，不进帧队列
        if (nalInfo == 8) { cachedPps = data; return; }  // PPS 仅作 csd，不进帧队列
        boolean keyFrame = (nalInfo == 5);   // 只有完整 IDR 才算关键帧
        if (waitingKeyFrame) {
            if (!keyFrame) {
                maybeSendPli(receivedNs);
                return;
            }
            waitingKeyFrame = false;
            callback.onRtpDiag("first key frame nal=" + nalInfo + " len=" + data.length
                    + " after " + Math.round((receivedNs - keyFrameWaitStartNs) / 1_000_000.0) + "ms");
        }
        FrameSample sample = new FrameSample(data, rtpTimestamp, receivedNs);
        while (!frameQueue.offer(sample)) {
            frameQueue.poll();
        }
    }

    private void maybeSendPli(long nowNs) {
        if (!running) return;
        if (nowNs - lastPliNs < KEY_FRAME_PLI_INTERVAL_NS) return;
        if (!waitingKeyFrame) {
            lastPliNs = nowNs;
            return;
        }
        long elapsed = nowNs - keyFrameWaitStartNs;
        callback.onWaitingKeyFrame(elapsed / 1_000_000L, pliSent);

        // 超时且 PLI 已发够次数 → 重启会话（restartInProgress 防重入）
        if (pliSent >= MAX_PLI_BEFORE_RESTART && elapsed > WAIT_KEY_FRAME_TIMEOUT_NS
                && !restartInProgress) {
            Log.w(TAG, "no key frame after " + (elapsed / 1_000_000L) + "ms, restart session");
            restartSession();
            return;
        }
        // 有 RTCP 端口 + 已拿到 SSRC → 发 PLI
        if (serverRtcpPort > 0 && mediaSsrc != 0) {
            byte[] pli = RtcpFeedback.buildPli(0x54554e48, mediaSsrc);
            try {
                rtcpSocket.send(new DatagramPacket(pli, pli.length,
                        new InetSocketAddress(rtspHost, serverRtcpPort)));
                pliSent++;
                lastPliNs = nowNs;
                Log.i(TAG, "PLI #" + pliSent + " -> " + rtspHost + ":" + serverRtcpPort
                        + " ssrc=0x" + Integer.toHexString(mediaSsrc));
            } catch (IOException e) {
                Log.w(TAG, "PLI send failed", e);
                lastPliNs = nowNs;
            }
        } else {
            lastPliNs = nowNs;
            Log.i(TAG, "PLI skipped: rtcp=" + serverRtcpPort + " ssrc=0x"
                    + Integer.toHexString(mediaSsrc));
        }
    }

    private void restartSession() {
        restartInProgress = true;
        new Thread(() -> {
            synchronized (this) {
                if (!running) return;
                Log.i(TAG, "restartSession begin");
                closeSockets();
                frameQueue.clear();
                waitingKeyFrame = true;
                pliSent = 0;
                lastPliNs = 0;
                keyFrameWaitStartNs = System.nanoTime();
                cachedSps = null;
                cachedPps = null;
                resetReassembler();
                if (!openSession(lastUrl)) {
                    running = false;
                }
                restartInProgress = false;
                callback.onRtpDiag("restart done");
            }
        }, "UDP_RTSP_RESTART").start();
    }

    private void resetReassembler() {
        reorder.clear();
        lastFlushedSeq = -1;
        lastRtpTimestamp = -1;
        fuNalType = -1;
        fuAccumLen = 0;
        fuNextSeq = -1;
    }

    // ═══════════════════════════════════════════════════════════════
    // 解码（复用 LowLatencyRtspPlayer 的低延迟解码配置）
    // ═══════════════════════════════════════════════════════════════

    private void decodeLoop() {
        MediaCodec codecLocal = null;
        try {
            while (running) {
                FrameSample sample = frameQueue.poll(100, TimeUnit.MILLISECONDS);
                if (sample == null) continue;
                if (codecLocal == null) {
                    // SPS/PPS 作为 csd（从当前会话缓存，非旧会话）
                    if (cachedSps == null || cachedPps == null) {
                        // SPS/PPS 未就绪，说明关键帧里没带或还没收到，等待下一帧
                        continue;
                    }
                    MediaFormat format = MediaFormat.createVideoFormat("video/avc", 1280, 720);
                    LowLatencyRtspPlayer.configureLowLatency(format);
                    format.setByteBuffer("csd-0", ByteBuffer.wrap(cachedSps));
                    format.setByteBuffer("csd-1", ByteBuffer.wrap(cachedPps));
                    MediaCodecInfo info = LowLatencyRtspPlayer.selectCodec("video/avc");
                    if (info == null) throw new IllegalStateException("no decoder for video/avc");
                    codecName = info.getName();
                    Log.w("TUN_DECODER", "UDP_SELF USING CODEC: " + codecName);
                    codecLocal = MediaCodec.createByCodecName(codecName);
                    codecLocal.configure(format, surface, null, 0);
                    codecLocal.setVideoScalingMode(MediaCodec.VIDEO_SCALING_MODE_SCALE_TO_FIT);
                    codecLocal.start();
                    codec = codecLocal;
                }
                if (firstStampUs == 0) firstStampUs = sample.rtpTimestamp;
                queueInput(codecLocal, sample);
                drainOutput(codecLocal);
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        } catch (Throwable t) {
            callback.onError(t.getMessage(), t);
            Log.e(TAG, "decoder failed", t);
        } finally {
            if (codecLocal != null) {
                try {
                    codecLocal.stop();
                } catch (Exception ignored) {
                }
                codecLocal.release();
            }
            codec = null;
        }
    }

    private void queueInput(MediaCodec codecLocal, FrameSample sample) {
        int index = codecLocal.dequeueInputBuffer(0);
        if (index < 0) return;
        ByteBuffer buffer = codecLocal.getInputBuffer(index);
        if (buffer == null) return;
        buffer.clear();
        int length = Math.min(sample.data.length, buffer.remaining());
        if (length < sample.data.length) {
            Log.w(TAG, "input buffer 不足: need=" + sample.data.length + " have=" + buffer.remaining());
        }
        buffer.put(sample.data, 0, length);
        long ptsUs = (sample.rtpTimestamp - firstStampUs) / 90;  // RTP 90kHz → us
        if (ptsUs < 0) ptsUs = 0;
        codecLocal.queueInputBuffer(index, 0, length, ptsUs, 0);
        inputTimesNs.offer(System.nanoTime());
    }

    private void drainOutput(MediaCodec codecLocal) {
        MediaCodec.BufferInfo info = new MediaCodec.BufferInfo();
        while (running) {
            int index = codecLocal.dequeueOutputBuffer(info, 0);
            if (index == MediaCodec.INFO_TRY_AGAIN_LATER) return;
            if (index == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) {
                MediaFormat fmt = codecLocal.getOutputFormat();
                int w = fmt.getInteger(MediaFormat.KEY_WIDTH);
                int h = fmt.getInteger(MediaFormat.KEY_HEIGHT);
                if (w != width || h != height) {
                    width = w;
                    height = h;
                    callback.onVideoSize(width, height);
                }
                continue;
            }
            if (index >= 0) {
                codecLocal.releaseOutputBuffer(index, true);
                inputTimesNs.poll();
                if (!decoded) {
                    decoded = true;
                    callback.onVideoDisplayed(codecName == null ? "udp-self" : codecName);
                }
            }
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // RTSP 保活
    // ═══════════════════════════════════════════════════════════════

    private void keepAliveLoop() {
        while (running) {
            try {
                Thread.sleep(20_000);
            } catch (InterruptedException e) {
                break;
            }
            if (!running) break;
            try {
                synchronized (rtspLock) {
                    int cseq = rtspControlCseq++;
                    BufferedWriter w = new BufferedWriter(new OutputStreamWriter(
                            rtspSocket.getOutputStream(), StandardCharsets.UTF_8));
                    w.write("OPTIONS " + lastUrl + " RTSP/1.0\r\n");
                    w.write("CSeq: " + cseq + "\r\n");
                    w.write("Session: " + sessionId + "\r\n\r\n");
                    w.flush();
                }
            } catch (IOException e) {
                Log.w(TAG, "keepalive failed", e);
            }
        }
    }

    private void releaseCodec() {
        MediaCodec c = codec;
        codec = null;
        if (c != null) {
            try {
                c.stop();
            } catch (Exception ignored) {
            }
            c.release();
        }
    }

    private void closeSockets() {
        DatagramSocket r = rtpSocket;
        rtpSocket = null;
        if (r != null) {
            try {
                r.close();
            } catch (Exception ignored) {
            }
        }
        DatagramSocket rc = rtcpSocket;
        rtcpSocket = null;
        if (rc != null) {
            try {
                rc.close();
            } catch (Exception ignored) {
            }
        }
        Socket s = rtspSocket;
        rtspSocket = null;
        if (s != null) {
            try {
                s.close();
            } catch (IOException ignored) {
            }
        }
    }

    // ═══════════════════════════════════════════════════════════════
    // RTP 解析
    // ═══════════════════════════════════════════════════════════════

    private static final class RtpPacket {
        final int seq;
        final int timestamp;
        final int ssrc;
        final byte[] payload;

        RtpPacket(int seq, int timestamp, int ssrc, byte[] payload) {
            this.seq = seq;
            this.timestamp = timestamp;
            this.ssrc = ssrc;
            this.payload = payload;
        }
    }

    private static RtpPacket parseRtp(byte[] data, int offset, int length) {
        int version = (data[offset] & 0xff) >> 6;
        if (version != 2) return null;
        int seq = ((data[offset + 2] & 0xff) << 8) | (data[offset + 3] & 0xff);
        int timestamp = ((data[offset + 4] & 0xff) << 24)
                | ((data[offset + 5] & 0xff) << 16)
                | ((data[offset + 6] & 0xff) << 8)
                | (data[offset + 7] & 0xff);
        int ssrc = ((data[offset + 8] & 0xff) << 24)
                | ((data[offset + 9] & 0xff) << 16)
                | ((data[offset + 10] & 0xff) << 8)
                | (data[offset + 11] & 0xff);
        int csrcCount = data[offset] & 0x0f;
        int headerLen = 12 + csrcCount * 4;
        if (headerLen > length) return null;
        byte[] payload = new byte[length - headerLen];
        System.arraycopy(data, offset + headerLen, payload, 0, payload.length);
        return new RtpPacket(seq, timestamp, ssrc, payload);
    }
}
