package com.tunnathub.app.rc

import com.tunnathub.app.RcMsg
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.util.concurrent.atomic.AtomicInteger

/** 定时发布 Android 融合 RC 状态: 本地更新 UI, 同包发送给 V3s 输出链路。 */
class RcMsgTransport(
    private val socket: DatagramSocket,
    private val host: InetAddress = InetAddress.getByName("10.0.0.1"),
    private val port: Int = PORT,
    private val onLocalData: (RcMsg.Data) -> Unit
) : AutoCloseable {
    private val seq = AtomicInteger()

    fun publish(sample: RcInputSample, geteventFresh: Boolean, port40007Fresh: Boolean) {
        val packet = RcMsgCodec.encode(sample, seq.incrementAndGet(), geteventFresh, port40007Fresh)
        RcMsgCodec.decodeLocal(packet)?.let(onLocalData)
        socket.send(DatagramPacket(packet, packet.size, host, port))
    }

    override fun close() {
        socket.close()
    }

    companion object {
        const val PORT = 65531
    }
}
