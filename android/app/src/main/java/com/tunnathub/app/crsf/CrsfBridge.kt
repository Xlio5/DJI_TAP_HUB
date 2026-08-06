/**
 * CrsfBridge.kt — V3s crsf-bridge 模式网口 UDP 客户端
 *
 * 与 ubuntu/src/dji_rc.cpp 的 crsf-bridge 模式对应:
 *   V3s 把 UART0 收到的 CRSF 参数帧(0x28+) 转发到 UDP 65532,
 *   App 在此收帧; App 发的 CRSF 命令也经此端口 → V3s → UART0。
 *
 * 网口协议: [magic "CRSF" 4B][CRSF 帧], magic = 0x46534352 little-endian
 */
package com.tunnathub.app.crsf

import android.util.Log
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.util.concurrent.atomic.AtomicBoolean

object CrsfBridge {
    private const val TAG = "CrsfBridge"
    const val PORT = 65532
    const val MAGIC = 0x46534352  // "CRSF" little-endian on wire

    @Volatile
    var host: String = "192.168.144.66"
        private set

    private var socket: DatagramSocket? = null
    private var rxThread: Thread? = null
    private val running = AtomicBoolean(false)

    /** CRSF 帧接收回调 (App 收 UART0 上行的参数帧/遥测) */
    @Volatile
    var onFrame: ((ByteArray) -> Unit)? = null

    /** 启动 UDP 收线程 + 建立发送 socket */
    fun start(hostAddr: String) {
        stop()
        host = hostAddr
        running.set(true)
        try {
            socket = DatagramSocket().apply { soTimeout = 1000 }
            rxThread = Thread {
                val buf = ByteArray(4 + 62)
                while (running.get()) {
                    try {
                        val pkt = DatagramPacket(buf, buf.size)
                        socket?.receive(pkt)
                        if (pkt.length >= 5 && pkt.length <= 4 + 62) {
                            val data = pkt.data.copyOfRange(0, pkt.length)
                            val magic = (data[0].toInt() and 0xFF) or
                                ((data[1].toInt() and 0xFF) shl 8) or
                                ((data[2].toInt() and 0xFF) shl 16) or
                                ((data[3].toInt() and 0xFF) shl 24)
                            if (magic == MAGIC) {
                                onFrame?.invoke(data.copyOfRange(4, data.size))
                            }
                        }
                    } catch (e: Exception) {
                        if (e is java.net.SocketTimeoutException) continue
                        if (running.get()) Log.w(TAG, "rx err: $e")
                    }
                }
            }.apply { isDaemon = true; start() }
            Log.i(TAG, "started @ $host:$PORT")
        } catch (e: Exception) {
            Log.e(TAG, "start fail: $e")
            running.set(false)
        }
    }

    /** 发送 CRSF 帧到 V3s (App → UART0) */
    fun sendFrame(frame: ByteArray) {
        if (frame.size > 62) return
        val sock = socket ?: return
        try {
            val pkt = ByteArray(4 + frame.size)
            // magic "CRSF" little-endian
            pkt[0] = (MAGIC and 0xFF).toByte()
            pkt[1] = ((MAGIC shr 8) and 0xFF).toByte()
            pkt[2] = ((MAGIC shr 16) and 0xFF).toByte()
            pkt[3] = ((MAGIC shr 24) and 0xFF).toByte()
            frame.copyInto(pkt, 4)
            val addr = InetAddress.getByName(host)
            sock.send(DatagramPacket(pkt, pkt.size, addr, PORT))
        } catch (e: Exception) {
            Log.w(TAG, "send err: $e")
        }
    }

    fun stop() {
        running.set(false)
        socket?.close()
        socket = null
        rxThread?.join(2000)
        rxThread = null
    }
}
