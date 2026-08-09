package com.tunnathub.app.video;

import java.io.ByteArrayOutputStream;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * 将 H264 NAL 按 RTP timestamp / marker 聚合成 Access Unit。
 *
 * <p>作用类似 GStreamer h264parse 的低配版：MediaCodec 每次收到完整 AU，而不是零散 NAL。</p>
 */
final class H264AccessUnitAssembler {
    static final class AccessUnit {
        final byte[] data;
        final long rtpTimestamp;
        final long receivedNs;
        final boolean containsKeyFrame;

        AccessUnit(byte[] data, long rtpTimestamp, long receivedNs, boolean containsKeyFrame) {
            this.data = data;
            this.rtpTimestamp = rtpTimestamp;
            this.receivedNs = receivedNs;
            this.containsKeyFrame = containsKeyFrame;
        }
    }

    private final ByteArrayOutputStream pending = new ByteArrayOutputStream(128 * 1024);
    private long pendingTimestamp = Long.MIN_VALUE;
    private long lastReceivedNs;
    private boolean pendingKeyFrame;

    List<AccessUnit> addNal(byte[] annexBNal, long rtpTimestamp, long receivedNs, int nalType, boolean marker) {
        List<AccessUnit> output = new ArrayList<>(2);
        if (hasPending() && pendingTimestamp != rtpTimestamp) {
            output.add(flushPending());
        }
        if (!hasPending()) {
            pendingTimestamp = rtpTimestamp;
        }
        pending.write(annexBNal, 0, annexBNal.length);
        lastReceivedNs = receivedNs;
        pendingKeyFrame |= nalType == 5;
        if (marker) {
            output.add(flushPending());
        }
        return output;
    }

    List<AccessUnit> flush() {
        if (!hasPending()) return Collections.emptyList();
        return Collections.singletonList(flushPending());
    }

    void reset() {
        pending.reset();
        pendingTimestamp = Long.MIN_VALUE;
        lastReceivedNs = 0;
        pendingKeyFrame = false;
    }

    private boolean hasPending() {
        return pending.size() > 0;
    }

    private AccessUnit flushPending() {
        AccessUnit unit = new AccessUnit(
                pending.toByteArray(),
                pendingTimestamp,
                lastReceivedNs,
                pendingKeyFrame);
        reset();
        return unit;
    }
}
