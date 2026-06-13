/**
 * EcmBridge.kt — UDP 隧道桥接 (WiFi 模式)
 *
 * 通过 WiFi/UDP socket 收发原始 IP 包，替代 USB Host API。
 * RK3588 和 Android 在同一 WiFi 网段 (172.24.91.x)，
 * 无需 ECM/RNDIS USB 网卡，直接用标准 socket。
 *
 * 双协程:
 *   Coroutine 1 (tunToUdp): TUN.read() → UDP send → RK3588
 *   Coroutine 2 (udpToTun): UDP recv → TUN.write()
 *
 * 无帧协议！UDP 数据报文直接携带原始 IP 包。
 */

package com.tunnathub.app.usb

import android.os.ParcelFileDescriptor
import android.util.Log
import kotlinx.coroutines.*
import java.io.FileInputStream
import java.io.FileOutputStream
import java.net.*
import kotlin.coroutines.coroutineContext

class EcmBridge(
    private val tunFd: ParcelFileDescriptor,
    /** VpnService.protect() — 将 UDP socket 排除在 VPN 路由之外 */
    private val protect: ((DatagramSocket) -> Boolean),
    /** RK3588 地址 (默认 WiFi IP) */
    private val serverAddr: String = "172.24.91.28"
) {
    companion object {
        private const val TAG = "EcmBridge"
        const val UDP_PORT = 8899
        private const val MAX_IP_PACKET = 1500
        private const val HB_INTERVAL_MS = 1000L
        private const val HB_TIMEOUT_MS = 5000L
        private const val HB_PING: Byte = 0x00
        private const val HB_PONG: Byte = 0x01
    }

    @Volatile var isConnected = false
        private set

    var onLinkStateChange: ((LinkState) -> Unit)? = null

    private var peerAddr = InetSocketAddress(serverAddr, UDP_PORT)
    private var udpSocket: DatagramSocket? = null

    /**
     * 启动双协程转发
     */
    suspend fun start(scope: CoroutineScope) {
        // 创建 UDP socket，绑定到任意可用地址
        val socket = DatagramSocket(null).apply {
            reuseAddress = true
            bind(InetSocketAddress(InetAddress.getByName("0.0.0.0"), 0))  // 随机端口
            soTimeout = 500
        }

        // 关键: protect() 防止 UDP 包被 VPN 路由回 TUN
        if (!protect(socket)) {
            Log.w(TAG, "protect() 返回 false，有回环风险")
        } else {
            Log.i(TAG, "protect() 成功")
        }

        udpSocket = socket
        val local = socket.localPort
        Log.i(TAG, "UDP socket 已绑定 :${local} → ${serverAddr}:${UDP_PORT}")

        isConnected = true
        onLinkStateChange?.invoke(LinkState.Connected)

        val tunInput = FileInputStream(tunFd.fileDescriptor)
        val tunOutput = FileOutputStream(tunFd.fileDescriptor)

        val job1 = scope.launch(Dispatchers.IO) { tunToUdpLoop(tunInput) }
        val job2 = scope.launch(Dispatchers.IO) { udpToTunLoop(tunOutput) }

        try { job1.join(); job2.join() }
        catch (_: CancellationException) {}
    }

    /* ── Coroutine 1: TUN → UDP ─────────────────────── */

    private suspend fun tunToUdpLoop(tunInput: FileInputStream) {
        val buf = ByteArray(MAX_IP_PACKET)
        var lastHb = System.currentTimeMillis()

        while (coroutineContext.isActive && isConnected) {
            try {
                val n = tunInput.read(buf)
                if (n <= 0) {
                    if (n < 0) break
                    delay(1)
                    if (System.currentTimeMillis() - lastHb >= HB_INTERVAL_MS) {
                        sendHeartbeat(HB_PING)
                        lastHb = System.currentTimeMillis()
                    }
                    continue
                }
                udpSocket?.send(DatagramPacket(buf, n, peerAddr))
                lastHb = System.currentTimeMillis()
            } catch (e: Exception) {
                if (coroutineContext.isActive) Log.e(TAG, "TUN→UDP", e)
                break
            }
        }
        Log.i(TAG, "TUN→UDP 退出")
    }

    /* ── Coroutine 2: UDP → TUN ─────────────────────── */

    private suspend fun udpToTunLoop(tunOutput: FileOutputStream) {
        val buf = ByteArray(MAX_IP_PACKET)
        var lastPkt = System.currentTimeMillis()

        while (coroutineContext.isActive && isConnected) {
            try {
                val packet = DatagramPacket(buf, buf.size)
                udpSocket?.receive(packet)
                val n = packet.length
                if (n <= 0) continue
                lastPkt = System.currentTimeMillis()

                if (n == 1) {
                    if (buf[0] == HB_PING) sendHeartbeat(HB_PONG)
                    continue
                }
                if (n <= MAX_IP_PACKET) tunOutput.write(buf, 0, n)
            } catch (e: SocketTimeoutException) {
                if (System.currentTimeMillis() - lastPkt > HB_TIMEOUT_MS && isConnected) {
                    Log.w(TAG, "对端超时")
                    isConnected = false
                    onLinkStateChange?.invoke(LinkState.Disconnected)
                    break
                }
            } catch (e: Exception) {
                if (coroutineContext.isActive) Log.e(TAG, "UDP→TUN", e)
                break
            }
        }
        isConnected = false
        onLinkStateChange?.invoke(LinkState.Disconnected)
        Log.i(TAG, "UDP→TUN 退出")
    }

    private fun sendHeartbeat(byte: Byte) {
        try { udpSocket?.send(DatagramPacket(byteArrayOf(byte), 1, peerAddr)) }
        catch (_: Exception) {}
    }

    fun disconnect() {
        isConnected = false
        onLinkStateChange?.invoke(LinkState.Disconnected)
        try { udpSocket?.close() } catch (_: Exception) {}
        udpSocket = null
    }
}

enum class LinkState { Disconnected, Connected, Reconnecting }
