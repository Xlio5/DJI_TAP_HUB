package org.easydarwin.video;

import java.util.List;

final class CodecNameRanker {
    private CodecNameRanker() {
    }

    static String bestName(List<String> names) {
        String best = null;
        int bestScore = Integer.MIN_VALUE;
        for (String name : names) {
            int score = score(name);
            if (best == null || score > bestScore) {
                best = name;
                bestScore = score;
            }
        }
        return best;
    }

    static int score(String name) {
        String lower = name.toLowerCase();
        int score = 0;
        if (lower.contains("low_latency") || lower.contains("low-latency")) score += 100;
        if (lower.startsWith("c2.qti") || lower.contains(".qti.")) score += 50;
        if (lower.startsWith("omx.qcom") || lower.contains(".qcom.")) score += 40;
        if (lower.startsWith("omx.google") || lower.startsWith("c2.android")) score -= 100;
        return score;
    }
}
