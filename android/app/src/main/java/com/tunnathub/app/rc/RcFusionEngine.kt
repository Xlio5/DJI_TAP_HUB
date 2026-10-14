package com.tunnathub.app.rc

/**
 * 将变化触发的 getevent 和低频 40007 合成为定时发布可复用的 RC 状态。
 *
 * **融合规则与新鲜窗口对齐 V3s 侧 `adb_rc_fuse()`**（ubuntu/src/adb_rc_fusion.cpp +
 * adb_rc_fusion.h）——两边读的是同一份 Android getevent，处理必须一致，否则同一条
 * 摇杆/按键在 App 显示与 V3s 输出上会对不上。
 *
 * 对齐后的规则（与 V3s 逐条对应）:
 *   1. **基线 = 40007**（提供按键 / mode / dial）—— 对应 `*out = *p40007_state`
 *   2. **getevent 新鲜时覆盖**：6 轴 + REC/SHOT —— 对应 `out->ch[i] = ge->ch[i]` / `out->rec = ge->rec`
 *   3. **L1~R3 用 OR 合并** —— 对应 `out->l1 = out->l1 || ge->l1`
 *      （40007 目前不产出这些位，实际等于 getevent 的值；保留 OR 以便 40007 以后支持）
 *   4. **新鲜窗口 getevent / 40007 都是 5s**（V3s `*_FRESH_US = 5000000`）
 *
 * 窗口从 80ms 放大到 5s 的意义：getevent 的 KEY 是**边沿触发**（按下只发一次 DOWN，
 * 按住期间没有新事件），窗口太短会让"按住"的按键在中途被判过期而闪回 0。
 */
object RcFusionEngine {
    /** getevent 新鲜窗口 —— 对齐 V3s `ADB_RC_GETEVENT_FRESH_US`(5s)。原 App 值 80ms 太短。 */
    const val GETEVENT_FRESH_MS = 5000L

    /** 40007 新鲜窗口 —— 对齐 V3s `ADB_RC_40007_FRESH_US`(5s)。 */
    const val PORT40007_FRESH_MS = 5000L

    @JvmStatic
    fun fuse(getevent: RcInputSample?, port40007: RcInputSample?, nowMs: Long): RcInputSample {
        val geFresh = isFresh(getevent, nowMs, GETEVENT_FRESH_MS)
        val p4Fresh = isFresh(port40007, nowMs, PORT40007_FRESH_MS)
        val ge = getevent.takeIf { geFresh }
        val base = port40007.takeIf { p4Fresh }

        // 轴: getevent 新鲜时由 getevent 覆盖, 否则回落 40007 (对齐 V3s)
        val axes = when {
            geFresh -> getevent!!.axes
            p4Fresh -> port40007!!.axes
            else -> List(6) { 0 }
        }
        return RcInputSample.complete(
            source = when {
                geFresh && p4Fresh -> "getevent+40007"
                geFresh -> "getevent"
                p4Fresh -> "40007"
                else -> "none"
            },
            axes = axes,
            // ── 基线 = 40007 (对齐 V3s: p4_fresh 时 *out = *p40007_state) ──
            btn = base?.btn ?: 0,
            stop = base?.stop ?: 0,
            focus = base?.focus ?: 0,
            rth = base?.rth ?: 0,
            c1 = base?.c1 ?: 0,
            c2 = base?.c2 ?: 0,
            c3 = base?.c3 ?: 0,
            up = base?.up ?: 0,
            down = base?.down ?: 0,
            left = base?.left ?: 0,
            right = base?.right ?: 0,
            aircraft = base?.aircraft ?: 0,
            back = base?.back ?: 0,
            dial = base?.dial ?: 0,
            mode = base?.mode ?: "?",
            // ── REC/SHOT: getevent 新鲜时整体覆盖 (对齐 V3s: out->rec = ge->rec) ──
            shot = if (geFresh) (getevent?.shot ?: 0) else (base?.shot ?: 0),
            rec = if (geFresh) (getevent?.rec ?: 0) else (base?.rec ?: 0),
            // ── L1~R3: OR 合并 (对齐 V3s: out->l1 = out->l1 || ge->l1) ──
            l1 = (base?.l1 ?: 0) or (ge?.l1 ?: 0),
            l2 = (base?.l2 ?: 0) or (ge?.l2 ?: 0),
            l3 = (base?.l3 ?: 0) or (ge?.l3 ?: 0),
            r1 = (base?.r1 ?: 0) or (ge?.r1 ?: 0),
            r2 = (base?.r2 ?: 0) or (ge?.r2 ?: 0),
            r3 = (base?.r3 ?: 0) or (ge?.r3 ?: 0),
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
