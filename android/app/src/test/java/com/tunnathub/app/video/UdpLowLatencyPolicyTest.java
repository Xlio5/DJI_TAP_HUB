package com.tunnathub.app.video;

public final class UdpLowLatencyPolicyTest {
    public static void main(String[] args) {
        usesShallowQueuesForLiveVideo();
        keepsReorderWindowBoundedBelowOneFrameBurst();
    }

    private static void usesShallowQueuesForLiveVideo() {
        assertEquals(1, UdpLowLatencyPolicy.FRAME_QUEUE_CAPACITY, "frame queue capacity");
        assertEquals(20, UdpLowLatencyPolicy.DECODER_POLL_TIMEOUT_MS, "decoder poll timeout");
        assertEquals(1_000L, UdpLowLatencyPolicy.INPUT_DEQUEUE_TIMEOUT_US, "input dequeue timeout");
    }

    private static void keepsReorderWindowBoundedBelowOneFrameBurst() {
        if (UdpLowLatencyPolicy.REORDER_WINDOW_PACKETS >= 64) {
            throw new AssertionError("reorder window should stay shallow for live video");
        }
        if (UdpLowLatencyPolicy.REORDER_WINDOW_PACKETS < 16) {
            throw new AssertionError("reorder window should still tolerate small RTP bursts");
        }
    }

    private static void assertEquals(long expected, long actual, String name) {
        if (expected != actual) {
            throw new AssertionError(name + " expected=" + expected + " actual=" + actual);
        }
    }
}
