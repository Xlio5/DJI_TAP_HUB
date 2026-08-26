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
    val l1: Int = 0,
    val l2: Int = 0,
    val l3: Int = 0,
    val r1: Int = 0,
    val r2: Int = 0,
    val r3: Int = 0,
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

        @JvmStatic
        fun complete(
            source: String,
            axes: List<Int>,
            btn: Int,
            stop: Int,
            focus: Int,
            shot: Int,
            rec: Int,
            rth: Int,
            c1: Int,
            c2: Int,
            c3: Int,
            up: Int,
            down: Int,
            left: Int,
            right: Int,
            aircraft: Int,
            back: Int,
            l1: Int,
            l2: Int,
            l3: Int,
            r1: Int,
            r2: Int,
            r3: Int,
            dial: Int,
            mode: String,
            timestampMs: Long
        ): RcInputSample = RcInputSample(
            source = source,
            axes = axes.normalizedAxes(),
            btn = bit(btn),
            stop = bit(stop),
            focus = bit(focus),
            shot = bit(shot),
            rec = bit(rec),
            rth = bit(rth),
            c1 = bit(c1),
            c2 = bit(c2),
            c3 = bit(c3),
            up = bit(up),
            down = bit(down),
            left = bit(left),
            right = bit(right),
            aircraft = bit(aircraft),
            back = bit(back),
            l1 = bit(l1),
            l2 = bit(l2),
            l3 = bit(l3),
            r1 = bit(r1),
            r2 = bit(r2),
            r3 = bit(r3),
            dial = dial.coerceIn(0, 255),
            mode = mode,
            timestampMs = timestampMs
        )

        internal fun bit(value: Int): Int = if (value != 0) 1 else 0
    }
}

internal fun List<Int>.normalizedAxes(): List<Int> =
    List(6) { idx -> (getOrNull(idx) ?: 0).coerceIn(-1024, 1024) }
