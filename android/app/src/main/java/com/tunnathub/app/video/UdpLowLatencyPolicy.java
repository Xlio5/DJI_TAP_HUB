package com.tunnathub.app.video;

/**
 * 自建 UDP 播放器的低延迟参数。
 *
 * <p>这些值按 QGC/GStreamer 的浅队列思路设置：宁可丢旧帧，也不把直播画面排队攒起来。</p>
 */
final class UdpLowLatencyPolicy {
    static final int FRAME_QUEUE_CAPACITY = 1;
    static final int REORDER_WINDOW_PACKETS = 48;
    static final int DECODER_POLL_TIMEOUT_MS = 20;
    static final long INPUT_DEQUEUE_TIMEOUT_US = 1_000L;
    static final long OUTPUT_DEQUEUE_TIMEOUT_US = 0L;
    static final int OUTPUT_DRAIN_LIMIT = 8;

    private UdpLowLatencyPolicy() {
    }
}
