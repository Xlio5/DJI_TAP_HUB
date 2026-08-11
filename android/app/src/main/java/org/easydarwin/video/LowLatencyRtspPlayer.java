package org.easydarwin.video;

import android.media.MediaCodecInfo;
import android.media.MediaCodecList;
import android.media.MediaFormat;
import android.os.Build;
import android.util.Log;

import java.nio.ByteBuffer;
import java.util.ArrayList;
import java.util.List;

/**
 * 低延迟硬解工具类。
 *
 * 这里只保留当前自建 UDP 播放器需要的 MediaCodec 选择、低延迟参数和 H264
 * 关键帧判断逻辑。
 */
public final class LowLatencyRtspPlayer {
    public static final String DEFAULT_H264_CODEC = "c2.qti.avc.decoder.low_latency";

    private static final String TAG = "LowLatencyRtspPlayer";
    private static final int VIDEO_CODEC_H264 = 0x1C;
    private static final int VIDEO_CODEC_H265 = 0xAE;
    private static volatile String sForcedCodecName;

    private LowLatencyRtspPlayer() {
    }

    public static final class FrameInfo {
        public byte[] buffer;
        public int offset;
        public int length;
        public int codec;
        public int type;
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

    public static String selectSoftwareH264CodecName() {
        List<String> decoders = listAvailableDecoders("video/avc");
        String firstSoftware = null;
        for (String name : decoders) {
            String lower = name.toLowerCase();
            if (lower.equals("c2.android.avc.decoder")) return name;
            if (lower.equals("omx.google.h264.decoder")) return name;
            if (firstSoftware == null && isSoftwareCodecName(name)) firstSoftware = name;
        }
        return firstSoftware;
    }

    public static MediaCodecInfo selectCodec(String mimeType) {
        List<MediaCodecInfo> candidates = new ArrayList<>();
        int numCodecs = MediaCodecList.getCodecCount();
        for (int i = 0; i < numCodecs; i++) {
            MediaCodecInfo codecInfo = MediaCodecList.getCodecInfoAt(i);
            if (!codecInfo.isEncoder() && codecMatch(mimeType, codecInfo)) {
                candidates.add(codecInfo);
            }
        }
        String forced = sForcedCodecName;
        if (forced != null) {
            for (MediaCodecInfo candidate : candidates) {
                if (forced.equals(candidate.getName())) {
                    return candidate;
                }
            }
            Log.w(TAG, "forced codec not found: " + forced);
        }
        MediaCodecInfo best = null;
        for (MediaCodecInfo candidate : candidates) {
            if (!isHardwareCodec(candidate)) continue;
            if (supportsLowLatencyFeature(candidate, mimeType)) return candidate;
            if (best == null) best = candidate;
        }
        if (best != null) return best;
        return candidates.isEmpty() ? null : candidates.get(0);
    }

    public static boolean codecMatch(String mimeType, MediaCodecInfo codecInfo) {
        for (String type : codecInfo.getSupportedTypes()) {
            if (mimeType.equalsIgnoreCase(type)) return true;
        }
        return false;
    }

    public static boolean supportsLowLatencyFeature(MediaCodecInfo codecInfo, String mimeType) {
        if (Build.VERSION.SDK_INT < 30) return false;
        try {
            MediaCodecInfo.CodecCapabilities caps = codecInfo.getCapabilitiesForType(mimeType);
            return caps != null && caps.isFeatureSupported(MediaCodecInfo.CodecCapabilities.FEATURE_LowLatency);
        } catch (Throwable ignored) {
            return false;
        }
    }

    public static void configureLowLatency(MediaFormat format) {
        if (Build.VERSION.SDK_INT >= 30) {
            format.setInteger(MediaFormat.KEY_LOW_LATENCY, 1);
            format.setInteger(MediaFormat.KEY_OUTPUT_REORDER_DEPTH, 0);   // 无重排，立即输出
            format.setInteger(MediaFormat.KEY_MAX_INPUT_SIZE, 0);
        }
        format.setInteger(MediaFormat.KEY_PRIORITY, 0);
        // OPERATING_RATE 设实际帧率附近，避免过高导致解码器缓存多帧平滑
        format.setInteger(MediaFormat.KEY_OPERATING_RATE, 90);
        // Qualcomm 专用低延迟：减少解码器输出缓冲帧数（DecBuffFrms），直击 285ms 缓存延迟
        putIfApi30(format, "vendor.qti-ext-dec-low-latency.enable", 1);
        putIfApi30(format, "vendor.qti-ext-dec-low-latency.delay-tolerance", 10000);
        putIfApi30(format, "vendor.qti-ext-dec-out-buf-count", 1);
    }

    private static void putIfApi30(MediaFormat format, String key, int value) {
        if (Build.VERSION.SDK_INT < 30) return;
        try {
            format.setInteger(key, value);
        } catch (Exception ignored) {
            // 非高通设备/解码器不支持该 key，忽略
        }
    }

    public static boolean isSyncFrame(FrameInfo frame) {
        if (frame == null || frame.buffer == null || frame.length <= 0) return false;
        if (frame.type == 1) return true;
        if (frame.codec != VIDEO_CODEC_H264 && frame.codec != VIDEO_CODEC_H265) return false;

        int offset = Math.max(0, frame.offset);
        int end = Math.min(frame.buffer.length, offset + frame.length);
        if (frame.codec == VIDEO_CODEC_H264) {
            return containsH264Nal(frame.buffer, offset, end, 5);
        }
        return containsH265Irap(frame.buffer, offset, end);
    }

    private static boolean containsH264Nal(byte[] data, int offset, int end, int targetType) {
        int start = findStartCode(data, offset, end);
        if (start < 0 && offset < end) {
            return (data[offset] & 0x1f) == targetType;
        }
        while (start >= 0) {
            int nalStart = skipStartCode(data, start, end);
            if (nalStart < end && (data[nalStart] & 0x1f) == targetType) return true;
            start = findStartCode(data, nalStart, end);
        }
        return false;
    }

    private static boolean containsH265Irap(byte[] data, int offset, int end) {
        int start = findStartCode(data, offset, end);
        if (start < 0 && offset + 1 < end) {
            int type = (data[offset] >> 1) & 0x3f;
            return type >= 16 && type <= 21;
        }
        while (start >= 0) {
            int nalStart = skipStartCode(data, start, end);
            if (nalStart + 1 < end) {
                int type = (data[nalStart] >> 1) & 0x3f;
                if (type >= 16 && type <= 21) return true;
            }
            start = findStartCode(data, nalStart, end);
        }
        return false;
    }

    private static int findStartCode(byte[] data, int offset, int end) {
        for (int i = offset; i + 3 < end; i++) {
            if (data[i] == 0 && data[i + 1] == 0) {
                if (data[i + 2] == 1) return i;
                if (i + 4 < end && data[i + 2] == 0 && data[i + 3] == 1) return i;
            }
        }
        return -1;
    }

    private static int skipStartCode(byte[] data, int start, int end) {
        if (start + 2 < end && data[start] == 0 && data[start + 1] == 0 && data[start + 2] == 1) {
            return start + 3;
        }
        if (start + 3 < end && data[start] == 0 && data[start + 1] == 0
                && data[start + 2] == 0 && data[start + 3] == 1) {
            return start + 4;
        }
        return start;
    }

    @SuppressWarnings("deprecation")
    private static boolean isHardwareCodec(MediaCodecInfo codecInfo) {
        if (Build.VERSION.SDK_INT >= 29) {
            return codecInfo.isHardwareAccelerated();
        }
        String name = codecInfo.getName().toLowerCase();
        return !isSoftwareCodecName(name);
    }

    private static boolean isSoftwareCodecName(String name) {
        String lower = name == null ? "" : name.toLowerCase();
        return lower.startsWith("omx.google.") || lower.startsWith("c2.android.")
                || lower.contains(".sw.") || lower.contains("software");
    }
}
