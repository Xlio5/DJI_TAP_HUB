package com.tunnathub.app.rc

/** Android 侧统一 RC 输入样本。axes 为 6 路中位归零值，范围约 -1024..1024。 */
data class RcInputSample(
    val source: String,
    val axes: List<Int>,
    val btn: Int = 0,
    val stop: Int = 0,
    val focus: Int = 0,
    val shot: Int = 0,
    val rec: Int = 0,
    val rth: Int = 0,
    val c1: Int = 0,
    val c2: Int = 0,
    val c3: Int = 0,
    val up: Int = 0,
    val down: Int = 0,
    val left: Int = 0,
    val right: Int = 0,
    val aircraft: Int = 0,
    val back: Int = 0,
    val dial: Int = 0,
    val mode: String = "?",
    val timestampMs: Long
) {
    companion object {
        @JvmStatic
        fun axes(source: String, axes: List<Int>, timestampMs: Long): RcInputSample =
            RcInputSample(source = source, axes = axes.normalizedAxes(), timestampMs = timestampMs)

        @JvmStatic
        fun full(
            source: String,
            axes: List<Int>,
            stop: Int,
            focus: Int,
            shot: Int,
            rec: Int,
            c1: Int,
            c2: Int,
            mode: String,
            timestampMs: Long
        ): RcInputSample = RcInputSample(
            source = source,
            axes = axes.normalizedAxes(),
            stop = bit(stop),
            focus = bit(focus),
            shot = bit(shot),
            rec = bit(rec),
            c1 = bit(c1),
            c2 = bit(c2),
            mode = mode,
            timestampMs = timestampMs
        )

        internal fun bit(value: Int): Int = if (value != 0) 1 else 0
    }
}

internal fun List<Int>.normalizedAxes(): List<Int> =
    List(6) { idx -> (getOrNull(idx) ?: 0).coerceIn(-1024, 1024) }
