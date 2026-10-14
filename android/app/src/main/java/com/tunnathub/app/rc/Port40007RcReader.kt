package com.tunnathub.app.rc

import java.io.InputStream
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.SocketException
import java.net.Socket

/** 解析 40007 端口和 V3s 串口同源的 DJI DUML RC 数据。 */
class Port40007RcReader(
    private val packetSource: PacketSource,
    private val onSample: (RcInputSample) -> Unit,
    private val nowMs: () -> Long = { System.currentTimeMillis() }
) {
    interface PacketSource {
        fun readPacket(): ByteArray?
    }

    /** 40007 内部状态: 供 AE/SPECIAL 帧合并用 (对齐 V3s adb_rc_merge_40007_state) */
    private var lastState: RcInputSample? = null

    fun runBlocking() {
        while (!Thread.currentThread().isInterrupted) {
            val packet = packetSource.readPacket() ?: continue
            val incoming = parsePacket(packet, nowMs()) ?: continue
            // 对齐 V3s dji_rc.cpp 的 40007 处理链 (原来 App 是"后到的帧直接覆盖", 缺了这两步):
            //   ① adb_rc_merge_40007_state()          -> AE 与 SPECIAL 帧合并
            //   ② adb_rc_strip_getevent_owned_buttons() -> rec/shot 归 getevent, 40007 侧置 0
            val merged = mergeFrames(lastState, incoming)
            val stripped = stripGeteventOwnedButtons(merged)
            lastState = stripped
            onSample(stripped)
        }
    }

    companion object {
        const val PORT = 40007
        private const val DUML_SOF = 0x55
        private const val DUML_MIN_PACKET = 13
        private const val DUML_MAX_PACKET = 1024

        /** 与 parseRcAe() 的 source 一致 */
        const val SOURCE_AE = "40007-rc-ae"
        /** 与 parseSpecial02() 的 source 一致 */
        const val SOURCE_SPECIAL = "40007-special-02"

        /**
         * 对齐 V3s `adb_rc_merge_40007_state()`:
         * **仅当**【新帧是 SPECIAL 且上一状态来自 AE】时合并 —— 以 **AE 为基线**,
         * 用 SPECIAL 覆盖 6 轴 / mode / stop / focus / shot / rec; 其余情况直接采用新帧。
         *
         * 这是 focus/shot 手感与 V3s 不一致的关键: App 原来不分帧型、后到者全量覆盖。
         */
        @JvmStatic
        fun mergeFrames(previous: RcInputSample?, incoming: RcInputSample): RcInputSample {
            if (previous == null) return incoming
            if (incoming.source != SOURCE_SPECIAL || previous.source != SOURCE_AE) return incoming
            return previous.copy(
                source = incoming.source,
                axes = incoming.axes,
                mode = incoming.mode,
                stop = incoming.stop,
                focus = incoming.focus,
                shot = incoming.shot,
                rec = incoming.rec,
                timestampMs = incoming.timestampMs
            )
        }

        /**
         * 对齐 V3s `adb_rc_strip_getevent_owned_buttons()`:
         * rec / shot 由 getevent 提供 (按键直读), 40007 侧这两个字段清 0。
         */
        @JvmStatic
        fun stripGeteventOwnedButtons(sample: RcInputSample): RcInputSample =
            if (sample.rec == 0 && sample.shot == 0) sample else sample.copy(rec = 0, shot = 0)

        @JvmStatic
        fun parsePacket(packet: ByteArray, nowMs: Long): RcInputSample? {
            val duml = parseDumlPacket(packet) ?: return null
            return when {
                duml.cmdSet == 0x06 && duml.cmdId == 0xAE -> parseRcAe(duml.payload, nowMs)
                duml.cmdSet == 0x01 && duml.cmdId == 0x02 -> parseSpecial02(duml.payload, nowMs)
                else -> null
            }
        }

        @JvmStatic
        fun parseRcAe(payload: ByteArray, nowMs: Long): RcInputSample? {
            if (payload.size < 17) return null
            val axes = MutableList(6) { idx ->
                val off = 5 + idx * 2
                val raw = u8(payload[off]) or (u8(payload[off + 1]) shl 8)
                (raw - 1024).coerceIn(-660, 660)
            }
            // 实机已确认 RC/0xAE 的 CH5/CH6 需要对调才对应物理控件。
            val tmp = axes[4]
            axes[4] = axes[5]
            axes[5] = tmp
            val b0 = u8(payload[0])
            val b1 = u8(payload[1])
            val b2 = u8(payload[2])
            return RcInputSample.complete(
                source = "40007-rc-ae",
                axes = axes,
                btn = (b1 shr 3) and 1,
                stop = (b0 shr 4) and 1,
                focus = (b0 shr 7) and 1,
                shot = (b0 shr 6) and 1,
                rec = b1 and 1,
                rth = (b0 shr 5) and 1,
                c1 = (b2 shr 2) and 1,
                c2 = (b2 shr 3) and 1,
                c3 = (b2 shr 4) and 1,
                up = (b1 shr 7) and 1,
                down = (b1 shr 6) and 1,
                left = (b1 shr 5) and 1,
                right = (b1 shr 4) and 1,
                aircraft = (b1 shr 2) and 1,
                back = (b1 shr 1) and 1,
                l1 = 0,
                l2 = 0,
                l3 = 0,
                r1 = 0,
                r2 = 0,
                r3 = 0,
                dial = u8(payload[4]),
                mode = modeName(b2 and 0x03),
                timestampMs = nowMs
            )
        }

        @JvmStatic
        fun parseSpecial02(payload: ByteArray, nowMs: Long): RcInputSample? {
            if (payload.size < 13) return null
            val axes = listOf(8, 19, 30, 41, 52, 63).map { start ->
                specialChannel(payload, start).coerceIn(-660, 660)
            }
            val p10 = u8(payload[10])
            val p12 = u8(payload[12])
            return RcInputSample.complete(
                source = "40007-special-02",
                axes = axes,
                btn = 0,
                stop = (p12 shr 4) and 1,
                focus = (p10 shr 6) and 1,
                shot = p12 and 1,
                rec = (p12 shr 5) and 1,
                rth = 0,
                c1 = 0,
                c2 = 0,
                c3 = 0,
                up = 0,
                down = 0,
                left = 0,
                right = 0,
                aircraft = 0,
                back = 0,
                l1 = 0,
                l2 = 0,
                l3 = 0,
                r1 = 0,
                r2 = 0,
                r3 = 0,
                dial = 0,
                mode = modeName((p12 shr 2) and 0x03),
                timestampMs = nowMs
            )
        }

        internal fun parseDumlPacket(packet: ByteArray): DumlPacket? {
            if (packet.size < DUML_MIN_PACKET) return null
            if (u8(packet[0]) != DUML_SOF) return null
            val verLen = u8(packet[1]) or (u8(packet[2]) shl 8)
            val len = verLen and 0x03FF
            val version = (verLen shr 10) and 0x3F
            if (version > 1 || len < DUML_MIN_PACKET || len > DUML_MAX_PACKET) return null
            if (packet.size < len || len < 13) return null
            return DumlPacket(
                raw = packet.copyOf(len),
                cmdSet = u8(packet[9]),
                cmdId = u8(packet[10]),
                payload = packet.copyOfRange(11, len - 2)
            )
        }

        private fun specialChannel(payload: ByteArray, start: Int): Int {
            val byteOff = start / 8
            val bitOff = start % 8
            var value = 0
            for (idx in 0 until 4) {
                if (byteOff + idx < payload.size) {
                    value = value or (u8(payload[byteOff + idx]) shl (idx * 8))
                }
            }
            var raw = (value shr bitOff) and 0x3FF
            val markByte = (start + 10) / 8
            val markBit = (start + 10) % 8
            if (markByte < payload.size) {
                raw = raw or (((u8(payload[markByte]) shr markBit) and 1) shl 10)
            }
            return raw - 1024
        }

        private fun modeName(bits: Int): String = when (bits) {
            0 -> "S"
            1 -> "N"
            2 -> "F"
            else -> "?"
        }

        private fun u8(value: Byte): Int = value.toInt() and 0xFF
    }

    data class DumlPacket(
        val raw: ByteArray,
        val cmdSet: Int,
        val cmdId: Int,
        val payload: ByteArray
    )
}

class DumlStreamPacketSource(
    private val input: InputStream
) : Port40007RcReader.PacketSource {
    private val parser = DumlStreamParser()
    private val queue = ArrayDeque<ByteArray>()
    private val buf = ByteArray(4096)

    override fun readPacket(): ByteArray? {
        while (queue.isEmpty()) {
            val n = input.read(buf)
            if (n < 0) return null
            parser.feed(buf.copyOf(n)).forEach(queue::addLast)
        }
        return queue.removeFirst()
    }
}

class Tcp40007PacketSource(
    private val host: String = "127.0.0.1",
    private val port: Int = Port40007RcReader.PORT
) : Port40007RcReader.PacketSource {
    private var socket: Socket? = null
    private var source: DumlStreamPacketSource? = null

    override fun readPacket(): ByteArray? {
        val streamSource = source ?: Socket(host, port).also { socket = it }.let {
            DumlStreamPacketSource(it.getInputStream())
        }.also {
            source = it
        }
        val packet = streamSource.readPacket()
        if (packet == null) {
            closeCurrent()
            throw SocketException("40007 tcp closed")
        }
        return packet
    }

    private fun closeCurrent() {
        source = null
        try { socket?.close() } catch (_: Exception) {}
        socket = null
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

class DumlStreamParser {
    private val buf = mutableListOf<Byte>()

    fun feed(data: ByteArray): List<ByteArray> {
        buf.addAll(data.toList())
        val packets = mutableListOf<ByteArray>()
        while (true) {
            val sof = buf.indexOf(0x55.toByte())
            if (sof < 0) {
                if (buf.size > 1024) buf.subList(0, buf.size - 3).clear()
                break
            }
            if (sof > 0) buf.subList(0, sof).clear()
            if (buf.size < 4) break
            val verLen = (buf[1].toInt() and 0xFF) or ((buf[2].toInt() and 0xFF) shl 8)
            val len = verLen and 0x03FF
            val version = (verLen shr 10) and 0x3F
            if (version > 1 || len < 13 || len > 1024) {
                buf.removeAt(0)
                continue
            }
            if (buf.size < len) break
            packets.add(buf.take(len).toByteArray())
            buf.subList(0, len).clear()
        }
        return packets
    }
}
