/**
 * RcMsg.kt — dji_rc UDP rcmsg 二进制协议解析 (与 ubuntu/src/dji_rc.cpp 的 RcMsg 结构对应)
 *
 * V3s dji_rc 通过 UDP 65530 发送遥控数据, 72 字节, 全小端:
 *   magic(u32 "RCM1") + version(u16) + size(u16) + seq(u32) + ts_us(u64)
 *   + ch[16](u16) + raw_ch[6](i16) + buttons(u32) + mode(u8) + dial(u8) + flags(u16)
 */
package com.tunnathub.app

import java.nio.ByteBuffer
import java.nio.ByteOrder

object RcMsg {
    const val PORT = 65530
    const val MAGIC = 0x314D4352  // "RCM1", little-endian on wire
    const val LENGTH = 72

    /** 解析结果: 与 MainActivity 的 rc* 状态变量一一对应 */
    data class Data(
        val chs: List<Int>,          // 16 通道 SBUS 值
        val rawChs: List<Int>,       // 6 个原始通道
        val mode: String,
        val btn: Int, val stop: Int, val focus: Int, val shot: Int, val rec: Int,
        val rth: Int, val c1: Int, val c2: Int, val c3: Int, val dial: Int,
        val up: Int, val down: Int, val left: Int, val right: Int,
        val aircraft: Int, val back: Int,
        // L1~R3 原始按键 (RCM1 buttons bit 15-20, getevent KEY_F1..F6)
        val l1: Int = 0, val l2: Int = 0, val l3: Int = 0,
        val r1: Int = 0, val r2: Int = 0, val r3: Int = 0
    )

    /**
     * 解析 72 字节 rcmsg 二进制。magic 不符或长度不足返回 null。
     */
    fun parse(buf: ByteArray): Data? {
        if (buf.size < LENGTH) return null
        val bb = ByteBuffer.wrap(buf).order(ByteOrder.LITTLE_ENDIAN)
        val magic = bb.int
        if (magic != MAGIC) return null
        // version(u16) size(u16) seq(u32) ts_us(u64) — 跳过
        bb.short; bb.short; bb.int; bb.long

        val chs = (0 until 16).map { bb.short.toInt() and 0xFFFF }
        val rawChs = (0 until 6).map { bb.short.toInt() }
        val buttons = bb.int.toLong() and 0xFFFFFFFFL
        val mode = bb.get().toInt() and 0xFF
        val dial = bb.get().toInt() and 0xFF
        // flags(u16) — 跳过
        bb.short

        fun bit(b: Int): Int = if (((buttons shr b) and 1L) != 0L) 1 else 0

        return Data(
            chs = chs,
            rawChs = rawChs,
            mode = when (mode) { 'S'.code -> "S"; 'N'.code -> "N"; 'F'.code -> "F"; else -> "?" },
            btn = bit(0), stop = bit(1), focus = bit(2), shot = bit(3), rec = bit(4),
            rth = bit(5), c1 = bit(6), c2 = bit(7), c3 = bit(8), dial = dial,
            up = bit(9), down = bit(10), left = bit(11), right = bit(12),
            aircraft = bit(13), back = bit(14),
            l1 = bit(15), l2 = bit(16), l3 = bit(17),
            r1 = bit(18), r2 = bit(19), r3 = bit(20)
        )
    }
}
