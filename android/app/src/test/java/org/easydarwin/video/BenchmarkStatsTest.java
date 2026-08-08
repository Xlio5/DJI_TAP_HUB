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

        Client.FrameInfo h264Idr = new Client.FrameInfo();
        h264Idr.codec = 0x1C;
        h264Idr.type = 2;
        h264Idr.buffer = new byte[] {0, 0, 0, 1, 0x65, 1, 2, 3};
        h264Idr.length = h264Idr.buffer.length;
        if (!LowLatencyRtspPlayer.isSyncFrame(h264Idr)) {
            throw new AssertionError("h264 idr should be sync frame");
        }

        Client.FrameInfo h264P = new Client.FrameInfo();
        h264P.codec = 0x1C;
        h264P.type = 2;
        h264P.buffer = new byte[] {0, 0, 0, 1, 0x41, 1, 2, 3};
        h264P.length = h264P.buffer.length;
        if (LowLatencyRtspPlayer.isSyncFrame(h264P)) {
            throw new AssertionError("h264 p frame should not be sync frame");
        }

        Client.FrameInfo h264RawIdr = new Client.FrameInfo();
        h264RawIdr.codec = 0x1C;
        h264RawIdr.type = 2;
        h264RawIdr.buffer = new byte[] {0x65, 1, 2, 3};
        h264RawIdr.length = h264RawIdr.buffer.length;
        if (!LowLatencyRtspPlayer.isSyncFrame(h264RawIdr)) {
            throw new AssertionError("raw h264 idr should be sync frame");
        }
    }
}
