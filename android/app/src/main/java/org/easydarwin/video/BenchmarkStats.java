package org.easydarwin.video;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public final class BenchmarkStats {
    public static final class Snapshot {
        public final String codecName;
        public final long elapsedMs;
        public final long firstFrameMs;
        public final int framesReceived;
        public final int inputQueued;
        public final int inputDropped;
        public final int inputUnavailable;
        public final int outputRendered;
        public final long decodeAvgMs;
        public final long decodeP50Ms;
        public final long decodeP95Ms;
        public final long callbackToInputAvgMs;
        public final long callbackToInputP95Ms;
        public final String error;

        private Snapshot(String codecName, long elapsedMs, long firstFrameMs, int framesReceived,
                         int inputQueued, int inputDropped, int inputUnavailable, int outputRendered,
                         long decodeAvgMs, long decodeP50Ms, long decodeP95Ms,
                         long callbackToInputAvgMs, long callbackToInputP95Ms, String error) {
            this.codecName = codecName;
            this.elapsedMs = elapsedMs;
            this.firstFrameMs = firstFrameMs;
            this.framesReceived = framesReceived;
            this.inputQueued = inputQueued;
            this.inputDropped = inputDropped;
            this.inputUnavailable = inputUnavailable;
            this.outputRendered = outputRendered;
            this.decodeAvgMs = decodeAvgMs;
            this.decodeP50Ms = decodeP50Ms;
            this.decodeP95Ms = decodeP95Ms;
            this.callbackToInputAvgMs = callbackToInputAvgMs;
            this.callbackToInputP95Ms = callbackToInputP95Ms;
            this.error = error;
        }

        public String oneLine() {
            String suffix = error == null ? "" : " err=" + error;
            return codecName + " first=" + firstFrameMs + "ms"
                    + " dec=" + decodeAvgMs + "/" + decodeP50Ms + "/" + decodeP95Ms + "ms"
                    + " cbIn=" + callbackToInputAvgMs + "/" + callbackToInputP95Ms + "ms"
                    + " frames=" + outputRendered
                    + " drop=" + inputDropped
                    + suffix;
        }
    }

    private final String codecName;
    private final List<Long> decodeDurationsNs = new ArrayList<>();
    private final List<Long> callbackToInputNs = new ArrayList<>();
    private long startedNs;
    private long firstFrameReceivedNs;
    private long firstRenderedNs;
    private int framesReceived;
    private int inputQueued;
    private int inputDropped;
    private int inputUnavailable;
    private int outputRendered;
    private String error;

    public BenchmarkStats(String codecName) {
        this.codecName = codecName;
    }

    public synchronized void markStarted(long nowNs) {
        startedNs = nowNs;
    }

    public synchronized void recordFrameReceived(long nowNs) {
        framesReceived++;
        if (firstFrameReceivedNs == 0) firstFrameReceivedNs = nowNs;
    }

    public synchronized void recordInputQueued(long nowNs, long receivedNs) {
        inputQueued++;
        if (receivedNs > 0) callbackToInputNs.add(nowNs - receivedNs);
    }

    public synchronized void recordInputDropped() {
        inputDropped++;
    }

    public synchronized void recordInputUnavailable() {
        inputUnavailable++;
    }

    public synchronized void recordRendered(long nowNs, long inputQueuedNs) {
        outputRendered++;
        if (firstRenderedNs == 0) firstRenderedNs = nowNs;
        if (inputQueuedNs > 0) decodeDurationsNs.add(nowNs - inputQueuedNs);
    }

    public synchronized void recordError(String message) {
        error = message;
    }

    public synchronized Snapshot snapshot(long nowNs) {
        long elapsedMs = startedNs == 0 ? 0 : nsToMs(nowNs - startedNs);
        long firstFrameMs = firstRenderedNs == 0 || startedNs == 0 ? -1 : nsToMs(firstRenderedNs - startedNs);
        return new Snapshot(codecName, elapsedMs, firstFrameMs, framesReceived, inputQueued,
                inputDropped, inputUnavailable, outputRendered,
                averageMs(decodeDurationsNs), percentileMs(decodeDurationsNs, 0.50),
                percentileMs(decodeDurationsNs, 0.95), averageMs(callbackToInputNs),
                percentileMs(callbackToInputNs, 0.95), error);
    }

    private static long averageMs(List<Long> values) {
        if (values.isEmpty()) return -1;
        long total = 0;
        for (Long value : values) total += value;
        return nsToMs(total / values.size());
    }

    private static long percentileMs(List<Long> values, double percentile) {
        if (values.isEmpty()) return -1;
        List<Long> sorted = new ArrayList<>(values);
        Collections.sort(sorted);
        int index = (int) Math.ceil(percentile * sorted.size()) - 1;
        index = Math.max(0, Math.min(index, sorted.size() - 1));
        return nsToMs(sorted.get(index));
    }

    private static long nsToMs(long ns) {
        return Math.round(ns / 1_000_000.0);
    }
}
