package org.easydarwin.video;

import android.content.Context;
import android.media.MediaCodec;
import android.media.MediaCodecInfo;
import android.media.MediaCodecList;
import android.media.MediaFormat;
import android.os.Build;
import android.util.Log;
import android.view.Surface;

import com.tunnathub.app.video.VpnNetworkBinder;

import java.io.IOException;
import java.nio.ByteBuffer;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;
import java.util.Queue;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.TimeUnit;

public final class LowLatencyRtspPlayer implements Client.SourceCallBack, RtspPlayerSession {
    public interface Callback {
        void onVideoDisplayed(String codecName);
        void onVideoSize(int width, int height);
        void onTimeout();
        void onUnsupportedVideo();
        void onError(String message, Throwable error);
        default void onStats(BenchmarkStats.Snapshot snapshot) {}
        default void onWaitingKeyFrame(long elapsedMs, int restarts) {}
    }

    private static final class FrameSample {
        final Client.FrameInfo frame;
        final long receivedNs;

        FrameSample(Client.FrameInfo frame, long receivedNs) {
            this.frame = frame;
            this.receivedNs = receivedNs;
        }
    }

    private static final String TAG = "LowLatencyRtspPlayer";
    private static final int VIDEO_CODEC_H264 = 0x1C;
    private static final int VIDEO_CODEC_H265 = 0xAE;
    private static final long KEY_FRAME_RESTART_NS = 5_000_000_000L;
    private static final int MAX_KEY_FRAME_RESTARTS = 8;
    public static final String DEFAULT_H264_CODEC = "c2.qti.avc.decoder.low_latency";
    private static volatile String sForcedCodecName = null;

    private final Context context;
    private final Surface surface;
    private final Callback callback;
    private final ArrayBlockingQueue<FrameSample> videoQueue = new ArrayBlockingQueue<>(1);

    private volatile boolean running;
    private Thread decoderThread;
    private Client client;
    private String currentUrl;
    private int currentTransportType;
    private BenchmarkStats stats = new BenchmarkStats("auto");
    private int channel;
    private boolean processBoundToVpn;
    private boolean waitingKeyFrame = true;
    private boolean restartingForKeyFrame;
    private int keyFrameRestarts;
    private long lastKeyFrameNoticeNs;
    private int debugVideoFrames;
    private long firstVideoFrameNs;
    private short width;
    private short height;

    public LowLatencyRtspPlayer(Context context, Surface surface, Callback callback) {
        this.context = context.getApplicationContext();
        this.surface = surface;
        this.callback = callback;
    }

    public static void setForcedCodec(String name) {
        if (name == null || name.length() == 0 || "auto".equals(name)) {
            sForcedCodecName = null;
        } else {
            sForcedCodecName = name;
        }
        Log.i(TAG, "setForcedCodec: " + getForcedCodec());
    }

    public static String getForcedCodec() {
        return sForcedCodecName == null ? "auto" : sForcedCodecName;
    }

    public static List<String> listAvailableDecoders() {
        List<String> list = new ArrayList<>();
        list.addAll(listAvailableDecoders("video/avc"));
        for (String name : listAvailableDecoders("video/hevc")) {
            if (!list.contains(name)) list.add(name);
        }
        return list;
    }

    public static List<String> listAvailableDecoders(String mimeType) {
        List<String> list = new ArrayList<>();
        int numCodecs = MediaCodecList.getCodecCount();
        for (int i = 0; i < numCodecs; i++) {
            MediaCodecInfo codecInfo = MediaCodecList.getCodecInfoAt(i);
            if (codecInfo.isEncoder()) continue;
            for (String type : codecInfo.getSupportedTypes()) {
                if (mimeType.equalsIgnoreCase(type)) {
                    if (!list.contains(codecInfo.getName())) list.add(codecInfo.getName());
                }
            }
        }
        return list;
    }

    public synchronized int start(String url, int transportType) {
        if (running) stop();
        running = true;
        currentUrl = url;
        currentTransportType = transportType;
        waitingKeyFrame = true;
        restartingForKeyFrame = false;
        keyFrameRestarts = 0;
        lastKeyFrameNoticeNs = 0;
        debugVideoFrames = 0;
        firstVideoFrameNs = 0;
        videoQueue.clear();
        stats = new BenchmarkStats(getForcedCodec());
        stats.markStarted(System.nanoTime());
        decoderThread = new Thread(this::decodeLoop, "LOW_LATENCY_DECODER");
        decoderThread.start();

        processBoundToVpn = VpnNetworkBinder.bindProcessToVpn(context);
        return openClientLocked(url, transportType);
    }

    public synchronized void stop() {
        running = false;
        videoQueue.clear();

        Thread thread = decoderThread;
        decoderThread = null;
        if (thread != null) {
            thread.interrupt();
            try {
                thread.join(1000);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }

        Client c = client;
        client = null;
        if (c != null) {
            c.unrigisterCallback(this);
            c.closeStream();
            try {
                c.close();
            } catch (IOException e) {
                Log.w(TAG, "close client failed", e);
            }
        }
        if (processBoundToVpn) {
            VpnNetworkBinder.clearProcessBinding(context);
            processBoundToVpn = false;
        }
    }

    private int openClientLocked(String url, int transportType) {
        client = new Client(context);
        channel = client.registerCallback(this);
        Log.i(TAG, "open rtsp: " + url);
        return client.openStream(channel, url, transportType, 1,
                Client.EASY_SDK_VIDEO_FRAME_FLAG, "", "");
    }

    private void closeClientLocked() {
        Client c = client;
        client = null;
        if (c == null) return;
        c.unrigisterCallback(this);
        c.closeStream();
        try {
            c.close();
        } catch (IOException e) {
            Log.w(TAG, "close client failed", e);
        }
    }

    @Override
    public void onSourceCallBack(int channelId, int channelPtr, int frameType, Client.FrameInfo frameInfo) {
        if (!running) return;
        if (frameType == 0) {
            callback.onTimeout();
            return;
        }
        if (frameType != Client.EASY_SDK_VIDEO_FRAME_FLAG || frameInfo == null) return;
        if (frameInfo.codec != VIDEO_CODEC_H264 && frameInfo.codec != VIDEO_CODEC_H265) {
            callback.onUnsupportedVideo();
            return;
        }
        if (frameInfo.width == 0 || frameInfo.height == 0) return;
        long receivedNs = System.nanoTime();
        if (firstVideoFrameNs == 0) firstVideoFrameNs = receivedNs;
        debugVideoFrames++;
        if (debugVideoFrames <= 12 || debugVideoFrames % 300 == 0) {
            Log.i(TAG, "video frame #" + debugVideoFrames
                    + " codec=" + frameInfo.codec
                    + " type=" + frameInfo.type
                    + " size=" + frameInfo.width + "x" + frameInfo.height
                    + " len=" + frameInfo.length
                    + " nal=" + describeNalTypes(frameInfo)
                    + " head=" + hexPrefix(frameInfo.buffer, frameInfo.offset, frameInfo.length)
                    + " waitingKey=" + waitingKeyFrame);
        }
        stats.recordFrameReceived(receivedNs);
        if (frameInfo.width != width || frameInfo.height != height) {
            width = frameInfo.width;
            height = frameInfo.height;
            callback.onVideoSize(width, height);
        }
        boolean syncFrame = isSyncFrame(frameInfo);
        if (waitingKeyFrame && !syncFrame) {
            maybeRestartForMissingKeyFrame(receivedNs);
            return;
        }
        if (waitingKeyFrame) {
            Log.i(TAG, "first key frame after "
                    + Math.round((receivedNs - firstVideoFrameNs) / 1_000_000.0)
                    + "ms, type=" + frameInfo.type
                    + ", len=" + frameInfo.length);
        }
        waitingKeyFrame = false;
        restartingForKeyFrame = false;
        offerLatest(new FrameSample(frameInfo, receivedNs));
    }

    private void maybeRestartForMissingKeyFrame(long nowNs) {
        long firstNs = firstVideoFrameNs;
        if (firstNs == 0) return;
        long elapsedNs = nowNs - firstNs;
        if (lastKeyFrameNoticeNs == 0 || nowNs - lastKeyFrameNoticeNs >= 1_000_000_000L) {
            lastKeyFrameNoticeNs = nowNs;
            callback.onWaitingKeyFrame(elapsedNs / 1_000_000L, keyFrameRestarts);
        }
        if (elapsedNs < KEY_FRAME_RESTART_NS || restartingForKeyFrame
                || keyFrameRestarts >= MAX_KEY_FRAME_RESTARTS) {
            return;
        }
        restartingForKeyFrame = true;
        final int attempt = keyFrameRestarts + 1;
        Log.w(TAG, "no key frame for " + (elapsedNs / 1_000_000L)
                + "ms, restart rtsp session #" + attempt);
        new Thread(() -> restartRtspForKeyFrame(attempt), "RTSP_KEY_RESTART").start();
    }

    private void restartRtspForKeyFrame(int attempt) {
        synchronized (this) {
            if (!running || !waitingKeyFrame) {
                restartingForKeyFrame = false;
                return;
            }
            keyFrameRestarts = attempt;
            firstVideoFrameNs = 0;
            debugVideoFrames = 0;
            lastKeyFrameNoticeNs = 0;
            videoQueue.clear();
            closeClientLocked();
            openClientLocked(currentUrl, currentTransportType);
            restartingForKeyFrame = false;
        }
    }

    @Override
    public void onMediaInfoCallBack(int channelId, Client.MediaInfo mi) {
        Log.i(TAG, "media info: " + mi);
    }

    @Override
    public void onEvent(int channel, int err, int info) {
        Log.i(TAG, "rtsp event err=" + err + ", info=" + info);
        if (err != 0 || info == 2 || info == 3) {
            callback.onError("rtsp event err=" + err + ", info=" + info, null);
        }
    }

    @Override
    public void sendSeiData(byte[] sei) {
    }

    private void offerLatest(FrameSample sample) {
        while (!videoQueue.offer(sample)) {
            videoQueue.poll();
            stats.recordInputDropped();
        }
    }

    public BenchmarkStats.Snapshot snapshotStats() {
        return stats.snapshot(System.nanoTime());
    }

    private void decodeLoop() {
        MediaCodec codec = null;
        String codecName = "";
        long firstStampUs = 0;
        boolean displayed = false;
        Queue<Long> inputTimesNs = new ArrayDeque<>();
        try {
            while (running) {
                FrameSample sample = videoQueue.poll(100, TimeUnit.MILLISECONDS);
                if (sample == null) continue;
                Client.FrameInfo frame = sample.frame;
                if (codec == null) {
                    String mime = frame.codec == VIDEO_CODEC_H264 ? "video/avc" : "video/hevc";
                    MediaFormat format = MediaFormat.createVideoFormat(mime, frame.width, frame.height);
                    configureLowLatency(format);
                    addCsd(format, frame, mime);
                    MediaCodecInfo codecInfo = selectCodec(mime);
                    if (codecInfo == null) throw new IllegalStateException("no decoder for " + mime);
                    codecName = codecInfo.getName();
                    stats = new BenchmarkStats(codecName);
                    stats.markStarted(System.nanoTime());
                    codec = MediaCodec.createByCodecName(codecName);
                    Log.w("TUN_DECODER", "LOW_LATENCY USING CODEC: " + codecName);
                    codec.configure(format, surface, null, 0);
                    codec.setVideoScalingMode(MediaCodec.VIDEO_SCALING_MODE_SCALE_TO_FIT);
                    codec.start();
                }
                if (firstStampUs == 0) firstStampUs = frame.stamp;
                queueInput(codec, sample, frame.stamp - firstStampUs, inputTimesNs);
                displayed |= drainOutput(codec, codecName, displayed, inputTimesNs);
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        } catch (Throwable t) {
            stats.recordError(t.getMessage());
            callback.onError(t.getMessage(), t);
            Log.e(TAG, "decoder failed", t);
        } finally {
            if (codec != null) {
                try {
                    codec.stop();
                } catch (Exception ignored) {
                }
                codec.release();
            }
        }
    }

    private boolean drainOutput(MediaCodec codec, String codecName, boolean displayed, Queue<Long> inputTimesNs) {
        MediaCodec.BufferInfo info = new MediaCodec.BufferInfo();
        boolean rendered = displayed;
        while (true) {
            int index = codec.dequeueOutputBuffer(info, 0);
            if (index == MediaCodec.INFO_TRY_AGAIN_LATER) return rendered;
            if (index == MediaCodec.INFO_OUTPUT_FORMAT_CHANGED) {
                Log.i(TAG, "output format: " + codec.getOutputFormat());
                continue;
            }
            if (index >= 0) {
                codec.releaseOutputBuffer(index, true);
                Long inputQueuedNs = inputTimesNs.poll();
                stats.recordRendered(System.nanoTime(), inputQueuedNs == null ? 0 : inputQueuedNs);
                if (!rendered) {
                    callback.onVideoDisplayed(codecName);
                    rendered = true;
                }
                callback.onStats(snapshotStats());
            }
        }
    }

    private void queueInput(MediaCodec codec, FrameSample sample, long presentationTimeUs, Queue<Long> inputTimesNs) {
        int index = codec.dequeueInputBuffer(0);
        if (index < 0) {
            stats.recordInputUnavailable();
            return;
        }
        ByteBuffer buffer = codec.getInputBuffer(index);
        if (buffer == null) return;
        buffer.clear();
        Client.FrameInfo frame = sample.frame;
        int length = Math.min(frame.length, buffer.remaining());
        buffer.put(frame.buffer, frame.offset, length);
        codec.queueInputBuffer(index, 0, length, Math.max(0, presentationTimeUs), 0);
        long nowNs = System.nanoTime();
        inputTimesNs.offer(nowNs);
        stats.recordInputQueued(nowNs, sample.receivedNs);
    }

    private static MediaCodecInfo selectCodec(String mimeType) {
        List<MediaCodecInfo> candidates = new ArrayList<>();
        int numCodecs = MediaCodecList.getCodecCount();
        for (int i = 0; i < numCodecs; i++) {
            MediaCodecInfo codecInfo = MediaCodecList.getCodecInfoAt(i);
            if (codecInfo.isEncoder()) continue;
            if (codecMatch(mimeType, codecInfo)) candidates.add(codecInfo);
        }
        if (candidates.isEmpty()) return null;
        String forced = sForcedCodecName;
        if (forced != null) {
            for (MediaCodecInfo candidate : candidates) {
                if (forced.equals(candidate.getName())) return candidate;
            }
            Log.w(TAG, "forced codec not found: " + forced);
        }
        MediaCodecInfo best = null;
        int bestScore = Integer.MIN_VALUE;
        for (MediaCodecInfo candidate : candidates) {
            int score = CodecNameRanker.score(candidate.getName());
            if (supportsLowLatencyFeature(candidate, mimeType)) score += 75;
            if (best == null || score > bestScore) {
                best = candidate;
                bestScore = score;
            }
        }
        return best;
    }

    private static boolean codecMatch(String mimeType, MediaCodecInfo codecInfo) {
        for (String type : codecInfo.getSupportedTypes()) {
            if (type.equalsIgnoreCase(mimeType)) return true;
        }
        return false;
    }

    private static boolean supportsLowLatencyFeature(MediaCodecInfo codecInfo, String mimeType) {
        if (Build.VERSION.SDK_INT < 30) return false;
        try {
            MediaCodecInfo.CodecCapabilities caps = codecInfo.getCapabilitiesForType(mimeType);
            return caps != null && caps.isFeatureSupported(MediaCodecInfo.CodecCapabilities.FEATURE_LowLatency);
        } catch (Exception e) {
            return false;
        }
    }

    private static void configureLowLatency(MediaFormat format) {
        format.setInteger(MediaFormat.KEY_MAX_INPUT_SIZE, 0);
        if (Build.VERSION.SDK_INT >= 30) {
            put(format, "vendor.qti-ext-dec-low-latency.enable", 1);
            put(format, "low-latency", 1);
            put(format, "vendor.qti-ext-dec-low-latency.delay-tolerance", 10000);
            put(format, "vendor.qti-ext-dec-out-buf-count", 1);
            put(format, MediaFormat.KEY_OPERATING_RATE, 60);
            put(format, MediaFormat.KEY_PRIORITY, 0);
            put(format, MediaFormat.KEY_LATENCY, 1);
            put(format, MediaFormat.KEY_OUTPUT_REORDER_DEPTH, 0);
        }
    }

    private static void put(MediaFormat format, String key, int value) {
        try {
            format.setInteger(key, value);
        } catch (Exception ignored) {
        }
    }

    private static void addCsd(MediaFormat format, Client.FrameInfo frame, String mime) {
        if ("video/avc".equals(mime)) {
            byte[] sps = findNal(frame.buffer, frame.offset, frame.length, 7);
            byte[] pps = findNal(frame.buffer, frame.offset, frame.length, 8);
            if (sps != null) format.setByteBuffer("csd-0", ByteBuffer.wrap(sps));
            if (pps != null) format.setByteBuffer("csd-1", ByteBuffer.wrap(pps));
        } else {
            byte[] vpsSpsPps = findHevcConfig(frame.buffer, frame.offset, frame.length);
            if (vpsSpsPps != null) format.setByteBuffer("csd-0", ByteBuffer.wrap(vpsSpsPps));
        }
    }

    private static byte[] findNal(byte[] data, int offset, int length, int type) {
        int end = offset + length;
        int start = findStartCode(data, offset, end);
        if (start < 0) {
            if (offset < end && (data[offset] & 0x1f) == type) {
                byte[] out = new byte[length];
                System.arraycopy(data, offset, out, 0, out.length);
                return out;
            }
            return null;
        }
        while (start >= 0) {
            int header = start + startCodeLength(data, start);
            int next = findStartCode(data, header + 1, end);
            int nalEnd = next >= 0 ? next : end;
            if (header < end && (data[header] & 0x1f) == type) {
                byte[] out = new byte[nalEnd - start];
                System.arraycopy(data, start, out, 0, out.length);
                return out;
            }
            start = next;
        }
        return null;
    }

    private static String describeNalTypes(Client.FrameInfo frame) {
        if (frame.buffer == null || frame.length <= 0) return "-";
        if (frame.codec == VIDEO_CODEC_H264) {
            return describeH264NalTypes(frame.buffer, frame.offset, frame.length);
        }
        if (frame.codec == VIDEO_CODEC_H265) {
            return describeHevcNalTypes(frame.buffer, frame.offset, frame.length);
        }
        return "-";
    }

    private static String describeH264NalTypes(byte[] data, int offset, int length) {
        int end = offset + length;
        int start = findStartCode(data, offset, end);
        if (start < 0) return offset < end ? String.valueOf(data[offset] & 0x1f) : "-";
        StringBuilder sb = new StringBuilder();
        while (start >= 0 && sb.length() < 24) {
            int header = start + startCodeLength(data, start);
            if (header < end) {
                if (sb.length() > 0) sb.append(',');
                sb.append(data[header] & 0x1f);
            }
            start = findStartCode(data, header + 1, end);
        }
        return sb.length() == 0 ? "-" : sb.toString();
    }

    private static String describeHevcNalTypes(byte[] data, int offset, int length) {
        int end = offset + length;
        int start = findStartCode(data, offset, end);
        if (start < 0) return offset + 1 < end ? String.valueOf((data[offset] >> 1) & 0x3f) : "-";
        StringBuilder sb = new StringBuilder();
        while (start >= 0 && sb.length() < 24) {
            int header = start + startCodeLength(data, start);
            if (header + 1 < end) {
                if (sb.length() > 0) sb.append(',');
                sb.append((data[header] >> 1) & 0x3f);
            }
            start = findStartCode(data, header + 2, end);
        }
        return sb.length() == 0 ? "-" : sb.toString();
    }

    private static String hexPrefix(byte[] data, int offset, int length) {
        if (data == null || length <= 0) return "-";
        int count = Math.min(length, 12);
        StringBuilder sb = new StringBuilder(count * 3);
        for (int i = 0; i < count; i++) {
            if (i > 0) sb.append(' ');
            int v = data[offset + i] & 0xff;
            if (v < 16) sb.append('0');
            sb.append(Integer.toHexString(v));
        }
        return sb.toString();
    }

    static boolean isSyncFrame(Client.FrameInfo frame) {
        if (frame.type == 1) return true;
        if (frame.buffer == null || frame.length <= 0) return false;
        if (frame.codec == VIDEO_CODEC_H264) {
            return findNal(frame.buffer, frame.offset, frame.length, 5) != null
                    || findNal(frame.buffer, frame.offset, frame.length, 7) != null;
        }
        if (frame.codec == VIDEO_CODEC_H265) {
            return hasHevcSyncNal(frame.buffer, frame.offset, frame.length);
        }
        return false;
    }

    private static boolean hasHevcSyncNal(byte[] data, int offset, int length) {
        int end = offset + length;
        int start = findStartCode(data, offset, end);
        while (start >= 0) {
            int header = start + startCodeLength(data, start);
            int next = findStartCode(data, header + 2, end);
            if (header + 1 < end) {
                int type = (data[header] >> 1) & 0x3f;
                if ((type >= 16 && type <= 21) || type == 32 || type == 33 || type == 34) {
                    return true;
                }
            }
            start = next;
        }
        return false;
    }

    private static byte[] findHevcConfig(byte[] data, int offset, int length) {
        int end = offset + length;
        int first = -1;
        int lastEnd = -1;
        int start = findStartCode(data, offset, end);
        while (start >= 0) {
            int header = start + startCodeLength(data, start);
            int next = findStartCode(data, header + 2, end);
            int nalEnd = next >= 0 ? next : end;
            if (header + 1 < end) {
                int type = (data[header] >> 1) & 0x3f;
                if (type == 32 || type == 33 || type == 34) {
                    if (first < 0) first = start;
                    lastEnd = nalEnd;
                }
            }
            start = next;
        }
        if (first < 0 || lastEnd <= first) return null;
        byte[] out = new byte[lastEnd - first];
        System.arraycopy(data, first, out, 0, out.length);
        return out;
    }

    private static int findStartCode(byte[] data, int from, int end) {
        for (int i = from; i + 3 < end; i++) {
            if (data[i] == 0 && data[i + 1] == 0) {
                if (data[i + 2] == 1) return i;
                if (i + 4 < end && data[i + 2] == 0 && data[i + 3] == 1) return i;
            }
        }
        return -1;
    }

    private static int startCodeLength(byte[] data, int start) {
        return data[start + 2] == 1 ? 3 : 4;
    }
}
