package com.tunnathub.app.rc

import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.Socket
import java.nio.ByteBuffer
import java.nio.ByteOrder

/** 解析 40007 端口里的低频摇杆和按键数据。 */
class Port40007RcReader(
    private val packetSource: PacketSource,
    private val onSample: (RcInputSample) -> Unit,
    private val nowMs: () -> Long = { System.currentTimeMillis() }
) {
    interface PacketSource {
        fun readPacket(): ByteArray?
    }

    fun runBlocking() {
        while (!Thread.currentThread().isInterrupted) {
            val packet = packetSource.readPacket() ?: continue
            parsePacket(packet, nowMs())?.let(onSample)
        }
    }

    companion object {
        const val PORT = 40007

        @JvmStatic
        fun parsePacket(packet: ByteArray, nowMs: Long): RcInputSample? =
            parseSpecialControlProto(packet, nowMs)
                ?: parseVirtualStickProto(packet, nowMs)
                ?: parseCompactBytes(packet, nowMs)

        @JvmStatic
        fun parseSpecialControlProto(packet: ByteArray, nowMs: Long): RcInputSample? {
            val fields = ProtoLite.readVarintFields(packet)
            if (fields.keys.none { it in 1..22 }) return null
            val axes = List(6) { idx -> byteAxisToCentered(fields[5 + idx] ?: 128) }
            val mode = when ((fields[20] ?: 0).toInt()) {
                0 -> "S"
                1 -> "N"
                2 -> "F"
                else -> "?"
            }
            return RcInputSample(
                source = "40007-special",
                axes = axes,
                btn = bitField(fields[14]),
                focus = bitField(fields[19]),
                shot = bitField(fields[18]),
                rec = bitField(fields[3]),
                rth = bitField(fields[22]),
                c1 = bitField(fields[12]),
                c2 = bitField(fields[13]),
                mode = mode,
                timestampMs = nowMs
            )
        }

        @JvmStatic
        fun parseVirtualStickProto(packet: ByteArray, nowMs: Long): RcInputSample? {
            val fields = ProtoLite.readFixed32Fields(packet)
            if (!fields.keys.containsAll(listOf(2, 3, 4, 5))) return null
            val roll = fields[2] ?: 0f
            val pitch = fields[3] ?: 0f
            val yaw = fields[4] ?: 0f
            val throttle = fields[5] ?: 0f
            val axes = listOf(
                scaleFloat(roll, 30f),
                scaleFloat(pitch, 30f),
                scaleFloat(yaw, 180f),
                scaleFloat(throttle, 5f),
                0,
                0
            )
            return RcInputSample.axes("40007-virtual-stick", axes, nowMs)
        }

        @JvmStatic
        fun parseCompactBytes(packet: ByteArray, nowMs: Long): RcInputSample? {
            if (packet.size < 16) return null
            val axes = List(6) { idx ->
                val off = 2 + idx * 2
                if (off + 1 >= packet.size) 0 else {
                    val raw = (packet[off].toInt() and 0xFF) or ((packet[off + 1].toInt() and 0xFF) shl 8)
                    (raw - 1024).coerceIn(-1024, 1024)
                }
            }
            val buttons = packet[14].toInt() and 0xFF
            val mode = when (packet[15].toInt() and 0x03) {
                0 -> "S"
                1 -> "N"
                2 -> "F"
                else -> "?"
            }
            return RcInputSample.full(
                source = "40007-compact",
                axes = axes,
                stop = (buttons shr 0) and 1,
                focus = (buttons shr 1) and 1,
                shot = (buttons shr 2) and 1,
                rec = (buttons shr 3) and 1,
                c1 = (buttons shr 4) and 1,
                c2 = (buttons shr 5) and 1,
                mode = mode,
                timestampMs = nowMs
            )
        }

        private fun byteAxisToCentered(value: Long): Int =
            ((value.toInt().coerceIn(0, 255) - 128) * 1024 / 128).coerceIn(-1024, 1024)

        private fun bitField(value: Long?): Int = if ((value ?: 0L) != 0L) 1 else 0

        private fun scaleFloat(value: Float, maxAbs: Float): Int =
            (value.coerceIn(-maxAbs, maxAbs) * 1024f / maxAbs).toInt().coerceIn(-1024, 1024)
    }
}

class Tcp40007PacketSource(
    private val host: String,
    private val port: Int = Port40007RcReader.PORT
) : Port40007RcReader.PacketSource {
    private var socket: Socket? = null

    override fun readPacket(): ByteArray? {
        val s = socket ?: Socket(host, port).also { socket = it }
        val input = s.getInputStream()
        val lenHi = input.read()
        if (lenHi < 0) return null
        val lenLo = input.read()
        if (lenLo < 0) return null
        val len = ((lenHi and 0xFF) shl 8) or (lenLo and 0xFF)
        if (len <= 0 || len > 4096) return null
        val out = ByteArray(len)
        var off = 0
        while (off < len) {
            val n = input.read(out, off, len - off)
            if (n < 0) return null
            off += n
        }
        return out
    }
}

class Udp40007PacketSource(
    private val socket: DatagramSocket
) : Port40007RcReader.PacketSource {
    override fun readPacket(): ByteArray? {
        val buf = ByteArray(512)
        val pkt = DatagramPacket(buf, buf.size)
        socket.receive(pkt)
        return pkt.data.copyOf(pkt.length)
    }
}

internal object ProtoLite {
    fun readVarintFields(packet: ByteArray): Map<Int, Long> {
        val out = linkedMapOf<Int, Long>()
        var i = 0
        while (i < packet.size) {
            val key = readVarint(packet, i) ?: break
            i = key.next
            val field = (key.value ushr 3).toInt()
            when ((key.value and 0x07).toInt()) {
                0 -> {
                    val value = readVarint(packet, i) ?: break
                    i = value.next
                    out[field] = value.value
                }
                1 -> i += 8
                2 -> {
                    val len = readVarint(packet, i) ?: break
                    i = len.next + len.value.toInt()
                }
                5 -> i += 4
                else -> break
            }
        }
        return out
    }

    fun readFixed32Fields(packet: ByteArray): Map<Int, Float> {
        val out = linkedMapOf<Int, Float>()
        var i = 0
        while (i < packet.size) {
            val key = readVarint(packet, i) ?: break
            i = key.next
            val field = (key.value ushr 3).toInt()
            when ((key.value and 0x07).toInt()) {
                5 -> {
                    if (i + 4 > packet.size) break
                    out[field] = ByteBuffer.wrap(packet, i, 4).order(ByteOrder.LITTLE_ENDIAN).float
                    i += 4
                }
                0 -> {
                    val value = readVarint(packet, i) ?: break
                    i = value.next
                }
                1 -> i += 8
                2 -> {
                    val len = readVarint(packet, i) ?: break
                    i = len.next + len.value.toInt()
                }
                else -> break
            }
        }
        return out
    }

    private data class Varint(val value: Long, val next: Int)

    private fun readVarint(packet: ByteArray, offset: Int): Varint? {
        var result = 0L
        var shift = 0
        var i = offset
        while (i < packet.size && shift < 64) {
            val b = packet[i].toInt() and 0xFF
            result = result or ((b and 0x7F).toLong() shl shift)
            i++
            if ((b and 0x80) == 0) return Varint(result, i)
            shift += 7
        }
        return null
    }
}
