package com.tunnathub.app.video;

/**
 * 自建 UDP 播放器的低延迟参数。
 *
 * <p>按 QGC/GStreamer 浅队列思路设置：宁可丢旧帧，也不把直播画面排队攒起来。
 * 目标：RTP 到达 → 重组 → 解码 → 显示的端到端延迟尽量低。</p>
 *
 * <p>QGC 的 rtpjitterbuffer 默认缓冲较深（~2000ms），低延迟场景会调小。
 * 我们用时间窗口（20ms）而非包数窗口：超过 20ms 还没凑齐的乱序包直接丢弃（丢旧保新），
 * 避免为"等一个迟到的包"而累积排队延迟。</p>
 */
final class UdpLowLatencyPolicy {
    /** 解码帧队列容量：1 即只保留最新一帧（丢旧保新），模拟 QGC GL sink 的 "latest frame wins"。 */
    static final int FRAME_QUEUE_CAPACITY = 1;

    /** 乱序缓冲最大包数（兜底，防止时间窗口无限增长缓冲）。 */
    static final int REORDER_WINDOW_PACKETS = 48;

    /** RTP 乱序容忍时间窗口：超过此时间的乱序包视为迟到，直接丢弃/跳过空洞。
     *  实测 0 会导致偶发乱序触发 FU-A 丢帧（帧率 25→15），且 cbIn=2ms 证明 20ms 窗口几乎不等，
     *  因此保持 20ms 平衡稳定与延迟。 */
    static final long RTP_JITTER_MAX_DELAY_NS = 20_000_000L;   // 20ms，平衡稳定与低延迟

    /** 解码器 poll 帧队列超时。 */
    static final int DECODER_POLL_TIMEOUT_MS = 20;

    /** input buffer 获取超时。 */
    static final long INPUT_DEQUEUE_TIMEOUT_US = 1_000L;

    /** output buffer 获取超时（0 = 非阻塞，立即返回）。 */
    static final long OUTPUT_DEQUEUE_TIMEOUT_US = 0L;

    /** 每次 drain 最多释放的 output buffer 数（防止长时间空转）。 */
    static final int OUTPUT_DRAIN_LIMIT = 8;

    /** 只渲染最新帧（丢旧保新），模拟 QGC GL sink 行为。 */
    static final boolean RENDER_ONLY_LATEST_OUTPUT = true;

    private UdpLowLatencyPolicy() {
    }
}
