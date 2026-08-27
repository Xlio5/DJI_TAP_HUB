package com.tunnathub.app.rc

import com.tunnathub.app.RcMsg
import java.nio.ByteBuffer
import java.nio.ByteOrder

/** 将 Android 融合后的 RC 状态编码为原有 RCM1 兼容消息。 */
object RcMsgCodec {
    private const val FLAG_GETEVENT_FRESH = 1
    private const val FLAG_40007_FRESH = 2
    private const val FLAG_ANDROID_FUSED = 4

    @JvmStatic
    fun encode(
        sample: RcInputSample,
        seq: Int,
        geteventFresh: Boolean,
        port40007Fresh: Boolean
    ): ByteArray {
        val raw = sample.axes.normalizedAxes()
        // ch7-16 扩展通道默认 1000 (与 V3s 回传一致; 1500 会导致双源交替时通道条闪动)
        val channels = List(16) { idx -> if (idx < raw.size) rawToUs(raw[idx]) else 1000 }
        val buf = ByteBuffer.allocate(RcMsg.LENGTH).order(ByteOrder.LITTLE_ENDIAN)
        buf.putInt(RcMsg.MAGIC)
        buf.putShort(1)
        buf.putShort(RcMsg.LENGTH.toShort())
        buf.putInt(seq)
        buf.putLong(sample.timestampMs * 1000L)
        channels.forEach { buf.putShort(it.toShort()) }
        raw.forEach { buf.putShort(it.toShort()) }
        buf.putInt(buttonBits(sample))
        buf.put(modeByte(sample.mode))
        buf.put(sample.dial.coerceIn(0, 255).toByte())
        var flags = FLAG_ANDROID_FUSED
        if (geteventFresh) flags = flags or FLAG_GETEVENT_FRESH
        if (port40007Fresh) flags = flags or FLAG_40007_FRESH
        buf.putShort(flags.toShort())
        return buf.array()
    }

    @JvmStatic
    fun decodeLocal(packet: ByteArray): RcMsg.Data? = RcMsg.parse(packet)

    @JvmStatic
    fun rawToUs(value: Int): Int =
        (1500 + value.coerceIn(-1024, 1024) * 500 / 1024).coerceIn(1000, 2000)

    @JvmStatic
    fun buttonBits(sample: RcInputSample): Int =
        ((sample.btn and 1) shl 0) or
            ((sample.stop and 1) shl 1) or
            ((sample.focus and 1) shl 2) or
            ((sample.shot and 1) shl 3) or
            ((sample.rec and 1) shl 4) or
            ((sample.rth and 1) shl 5) or
            ((sample.c1 and 1) shl 6) or
            ((sample.c2 and 1) shl 7) or
            ((sample.c3 and 1) shl 8) or
            ((sample.up and 1) shl 9) or
            ((sample.down and 1) shl 10) or
            ((sample.left and 1) shl 11) or
            ((sample.right and 1) shl 12) or
            ((sample.aircraft and 1) shl 13) or
            ((sample.back and 1) shl 14)

    private fun modeByte(mode: String): Byte =
        when (mode.firstOrNull()) {
            'S', 'N', 'F' -> mode.first().code.toByte()
            else -> '?'.code.toByte()
        }
}
