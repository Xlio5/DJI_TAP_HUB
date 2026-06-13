/**
 * FrameCodec.kt — USB 帧编解码器
 *
 * 与 protocol/frame.h 定义完全一致的 Kotlin 实现。
 *
 * 帧格式: [Magic(2B, 大端)][Length(2B, 大端)][Payload(N bytes)]
 *   Magic = 0x544E ("TN")
 *   Length = 0 → 心跳帧
 *   Length = 2 → Credit 帧（Phase 3）
 */

package com.tunnathub.app.proto

import java.nio.ByteBuffer
import java.nio.ByteOrder

object FrameCodec {

    // ── 帧常量 ──────────────────────────────────────────
    const val FRAME_MAGIC: Short = 0x544E.toShort()  // "TN" 大端
    const val FRAME_HEADER_LEN = 4                   // Magic(2) + Length(2)
    const val FRAME_MAX_PAYLOAD = 2048
    const val FRAME_MAX_LEN = FRAME_HEADER_LEN + FRAME_MAX_PAYLOAD

    // 心跳参数
    const val HEARTBEAT_INTERVAL_MS = 1000L
    const val HEARTBEAT_TIMEOUT_MS = 5000L  // Android 端判定断开的超时

    // ── 打包 ────────────────────────────────────────────
    /**
     * 将 IP 包封装为帧写入 buf。
     * @param buf     输出缓冲区（前 4 字节会被覆盖）
     * @param payload IP 包数据
     * @return 完整帧长度
     */
    fun pack(buf: ByteArray, payload: ByteArray): Int {
        require(payload.size <= FRAME_MAX_PAYLOAD) {
            "Payload 过长: ${payload.size} > $FRAME_MAX_PAYLOAD"
        }
        require(buf.size >= FRAME_HEADER_LEN + payload.size) {
            "缓冲区太小: ${buf.size} < ${FRAME_HEADER_LEN + payload.size}"
        }

        // Magic（大端）
        buf[0] = (FRAME_MAGIC.toInt() shr 8 and 0xFF).toByte()  // 0x54 'T'
        buf[1] = (FRAME_MAGIC.toInt() and 0xFF).toByte()         // 0x4E 'N'

        // Length（大端）
        val len = payload.size
        buf[2] = (len shr 8 and 0xFF).toByte()
        buf[3] = (len and 0xFF).toByte()

        // Payload
        System.arraycopy(payload, 0, buf, FRAME_HEADER_LEN, len)

        return FRAME_HEADER_LEN + len
    }

    /**
     * 打包心跳帧（Length=0）。
     * @param buf 输出缓冲区（至少 4 字节）
     */
    fun packHeartbeat(buf: ByteArray) {
        buf[0] = (FRAME_MAGIC.toInt() shr 8 and 0xFF).toByte()
        buf[1] = (FRAME_MAGIC.toInt() and 0xFF).toByte()
        buf[2] = 0
        buf[3] = 0
    }

    // ── 解包 ────────────────────────────────────────────
    /**
     * 校验并提取帧中 payload。
     * @return UnpackResult — 包含 payload 和类型信息；magic 不匹配时 payload 为 null
     */
    fun unpack(buf: ByteArray, totalLen: Int): UnpackResult {
        if (totalLen < FRAME_HEADER_LEN) {
            return UnpackResult.Error("帧不完整: $totalLen < $FRAME_HEADER_LEN")
        }

        // 校验 Magic
        val magic = ((buf[0].toInt() and 0xFF) shl 8) or (buf[1].toInt() and 0xFF)
        if (magic != FRAME_MAGIC.toInt() and 0xFFFF) {
            return UnpackResult.MagicMismatch
        }

        // 解析 Length（大端）
        val payloadLen = ((buf[2].toInt() and 0xFF) shl 8) or (buf[3].toInt() and 0xFF)

        if (payloadLen > FRAME_MAX_PAYLOAD) {
            return UnpackResult.Error("Payload 长度异常: $payloadLen > $FRAME_MAX_PAYLOAD")
        }

        if (FRAME_HEADER_LEN + payloadLen > totalLen) {
            return UnpackResult.Error("帧不完整: ${FRAME_HEADER_LEN + payloadLen} > $totalLen")
        }

        // 心跳帧
        if (payloadLen == 0) {
            return UnpackResult.Heartbeat
        }

        // Credit 帧
        if (payloadLen == 2) {
            val credit = ((buf[FRAME_HEADER_LEN].toInt() and 0xFF) shl 8) or
                         (buf[FRAME_HEADER_LEN + 1].toInt() and 0xFF)
            return UnpackResult.Credit(credit)
        }

        // 数据帧
        val payload = ByteArray(payloadLen)
        System.arraycopy(buf, FRAME_HEADER_LEN, payload, 0, payloadLen)
        return UnpackResult.Data(payload)
    }

    // ── 结果类型 ────────────────────────────────────────
    sealed class UnpackResult {
        /** 正常数据帧 */
        data class Data(val payload: ByteArray) : UnpackResult()

        /** 心跳帧 (PING/PONG) */
        object Heartbeat : UnpackResult()

        /** Credit 帧 */
        data class Credit(val value: Int) : UnpackResult()

        /** Magic 不匹配（帧同步错误） */
        object MagicMismatch : UnpackResult()

        /** 其他错误 */
        data class Error(val message: String) : UnpackResult()
    }
}
