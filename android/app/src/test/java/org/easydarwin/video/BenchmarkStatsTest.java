package org.easydarwin.video;

public final class BenchmarkStatsTest {
    public static void main(String[] args) {
        BenchmarkStats stats = new BenchmarkStats("c2.qti.avc.decoder.low_latency");
        stats.markStarted(1_000_000L);
        stats.recordFrameReceived(2_000_000L);
        stats.recordInputQueued(3_000_000L, 2_000_000L);
        stats.recordRendered(8_000_000L, 3_000_000L);
        stats.recordRendered(11_000_000L, 5_000_000L);
        stats.recordInputDropped();

        BenchmarkStats.Snapshot snapshot = stats.snapshot(12_000_000L);
        if (snapshot.firstFrameMs != 7) throw new AssertionError("firstFrameMs=" + snapshot.firstFrameMs);
        if (snapshot.decodeAvgMs != 6) throw new AssertionError("decodeAvgMs=" + snapshot.decodeAvgMs);
        if (snapshot.decodeP50Ms != 5) throw new AssertionError("decodeP50Ms=" + snapshot.decodeP50Ms);
        if (snapshot.decodeP95Ms != 6) throw new AssertionError("decodeP95Ms=" + snapshot.decodeP95Ms);
        if (snapshot.callbackToInputAvgMs != 1) throw new AssertionError("callbackToInputAvgMs=" + snapshot.callbackToInputAvgMs);
        if (snapshot.inputDropped != 1) throw new AssertionError("inputDropped=" + snapshot.inputDropped);
    }
}
