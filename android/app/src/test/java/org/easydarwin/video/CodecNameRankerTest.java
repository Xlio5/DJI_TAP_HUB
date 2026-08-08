package org.easydarwin.video;

import java.util.Arrays;
import java.util.List;

public final class CodecNameRankerTest {
    public static void main(String[] args) {
        List<String> names = Arrays.asList(
                "OMX.google.h264.decoder",
                "OMX.qcom.video.decoder.avc",
                "c2.qti.avc.decoder.low_latency");

        String selected = CodecNameRanker.bestName(names);
        if (!"c2.qti.avc.decoder.low_latency".equals(selected)) {
            throw new AssertionError("expected low-latency qti codec, got " + selected);
        }
    }
}
