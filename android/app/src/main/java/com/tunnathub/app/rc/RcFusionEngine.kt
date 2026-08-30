package com.tunnathub.app.rc

/** 将变化触发的 getevent 和低频 40007 合成为定时发布可复用的 RC 状态。 */
object RcFusionEngine {
    const val GETEVENT_FRESH_MS = 80L
    // 40007 实测 ~0.4Hz (2.5s/帧), 且服务端约 4s 主动断一次 TCP (App 0.3s 重连),
    // fresh 太短会在断开周期内 p4Fresh=false → 40007 按键/轴清 0;
    // 5000ms 覆盖 断开+重连 周期, 保持最后一次 40007 数据到下一帧。
    const val PORT40007_FRESH_MS = 5000L

    @JvmStatic
    fun fuse(getevent: RcInputSample?, port40007: RcInputSample?, nowMs: Long): RcInputSample {
        val geFresh = isFresh(getevent, nowMs, GETEVENT_FRESH_MS)
        val p4Fresh = isFresh(port40007, nowMs, PORT40007_FRESH_MS)
        val axes = when {
            geFresh -> getevent!!.axes
            p4Fresh -> port40007!!.axes
            else -> List(6) { 0 }
        }
        val keys = port40007.takeIf { p4Fresh }
        val geKeys = getevent.takeIf { geFresh }
        return RcInputSample.complete(
            source = when {
                geFresh && p4Fresh -> "getevent+40007"
                geFresh -> "getevent"
                p4Fresh -> "40007"
                else -> "none"
            },
            axes = axes,
            btn = keys?.btn ?: 0,
            stop = keys?.stop ?: 0,
            focus = keys?.focus ?: 0,
            // 修复: REC/SHOT 用 OR 合并 (getevent 活跃时 geKeys.rec/shot=0 非 null, ?: 不会回退到 40007,
            // 导致 40007 的 REC/SHOT 被 getevent 的 0 覆盖 → CH 不反映 40007 按键)。
            shot = (geKeys?.shot ?: 0) or (keys?.shot ?: 0),
            rec = (geKeys?.rec ?: 0) or (keys?.rec ?: 0),
            rth = keys?.rth ?: 0,
            c1 = keys?.c1 ?: 0,
            c2 = keys?.c2 ?: 0,
            c3 = keys?.c3 ?: 0,
            up = keys?.up ?: 0,
            down = keys?.down ?: 0,
            left = keys?.left ?: 0,
            right = keys?.right ?: 0,
            aircraft = keys?.aircraft ?: 0,
            back = keys?.back ?: 0,
            l1 = geKeys?.l1 ?: 0,
            l2 = geKeys?.l2 ?: 0,
            l3 = geKeys?.l3 ?: 0,
            r1 = geKeys?.r1 ?: 0,
            r2 = geKeys?.r2 ?: 0,
            r3 = geKeys?.r3 ?: 0,
            dial = keys?.dial ?: 0,
            mode = keys?.mode ?: "?",
            timestampMs = nowMs
        )
    }

    @JvmStatic
    fun shouldPublish(lastPublishMs: Long, nowMs: Long, intervalMs: Long = 20L): Boolean =
        nowMs - lastPublishMs >= intervalMs

    @JvmStatic
    fun isFresh(sample: RcInputSample?, nowMs: Long, windowMs: Long): Boolean =
        sample != null && nowMs - sample.timestampMs in 0..windowMs
}
