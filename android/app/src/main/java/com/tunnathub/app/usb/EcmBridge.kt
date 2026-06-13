/**
 * EcmBridge.kt — ECM/RNDIS UDP 隧道桥接
 *
 * 替换 UsbBridge (USB Host API + Bulk 端点)。
 * 通过 ECM/RNDIS 虚拟网卡 (usb0) 的 UDP socket 收发原始 IP 包。
 *
 * 双协程:
 *   Coroutine 1 (tunToUdp): TUN.read() → DatagramPacket → UDP socket → RK3588
 *   Coroutine 2 (udpToTun): UDP socket → DatagramPacket → TUN.write()
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

class EcmBridge(
    private val tunFd: ParcelFileDescriptor,
    /** 由 VpnService 提供，将 socket 排除在 VPN 路由之外（防止回环） */
    private val protect: ((DatagramSocket) -> Boolean)
) {
    companion object {
        private const val TAG = "EcmBridge"

        /** RK3588 usb0 监听端口 */
        const val UDP_PORT = 8899

        /** 最大 IP 包大小 (含 IP 头，对齐 TUN MTU 1400) */
        private const val MAX_IP_PACKET = 1500

        /** 心跳间隔 ms */
        private const val HB_INTERVAL_MS = 1000L

        /** 心跳超时 ms */
        private const val HB_TIMEOUT_MS = 5000L

        /** 心跳字节 */
        private const val HB_PING: Byte = 0x00
        private const val HB_PONG: Byte = 0x01
    }

    @Volatile var isConnected = false
        private set

    var onLinkStateChange: ((LinkState) -> Unit)? = null

    /** 对端地址 (RK3588 usb0:8899) */
    private var peerAddr = InetSocketAddress("10.0.0.1", UDP_PORT)

    private var udpSocket: DatagramSocket? = null

    /**
     * 查找 ECM/RNDIS 网卡接口名。
     * 返回匹配 usb0/usb1/rndis0 的接口名，找不到返回 null。
     */
    private fun findEcmInterface(): NetworkInterface? {
        val candidates = listOf("usb0", "usb1", "rndis0")
        val ifaces = NetworkInterface.getNetworkInterfaces()
        while (ifaces.hasMoreElements()) {
            val iface = ifaces.nextElement()
            if (iface.name in candidates && iface.isUp) {
                Log.i(TAG, "找到 ECM/RNDIS 接口: ${iface.name}")
                return iface
            }
        }
        return null
    }

    /**
     * 启动双协程转发
     */
    suspend fun start(scope: CoroutineScope) {
        val iface = findEcmInterface()
            ?: throw IllegalStateException(
                "未找到 ECM/RNDIS 网卡接口 (预期 usb0/rndis0)。请确认 USB Gadget 已连接。")

        // 获取接口上的 IPv4 地址
        val localIp = iface.interfaceAddresses
            ?.firstOrNull { it.address is Inet4Address }
            ?.address as? Inet4Address
            ?: InetAddress.getByName("0.0.0.0") as Inet4Address

        Log.i(TAG, "ECM 接口: ${iface.name}, 本端 IP: ${localIp.hostAddress}")

        // 创建 UDP socket 并绑定
        val socket = DatagramSocket(null).apply {
            reuseAddress = true
            bind(InetSocketAddress(localIp, UDP_PORT))
            soTimeout = 500  // 500ms 接收超时，允许周期性检查连接状态
        }

        // 关键: 将 socket 排除在 VPN 路由之外，防止数据包循环回 TUN
        if (!protect(socket)) {
            Log.w(TAG, "protect() 返回 false，socket 可能被 VPN 路由，有回环风险")
        } else {
            Log.i(TAG, "protect() 成功，socket 已排除在 VPN 路由之外")
        }

        udpSocket = socket
        Log.i(TAG, "UDP socket 已绑定 ${localIp.hostAddress}:$UDP_PORT → 10.0.0.1:$UDP_PORT")

        isConnected = true
        onLinkStateChange?.invoke(LinkState.Connected)

        val tunInput = FileInputStream(tunFd.fileDescriptor)
        val tunOutput = FileOutputStream(tunFd.fileDescriptor)

        val job1 = scope.launch(Dispatchers.IO) { tunToUdpLoop(tunInput) }
        val job2 = scope.launch(Dispatchers.IO) { udpToTunLoop(tunOutput) }

        try {
            job1.join()
            job2.join()
        } catch (_: CancellationException) {}
    }

    /* ── Coroutine 1: TUN → UDP ─────────────────────── */

    private suspend fun tunToUdpLoop(tunInput: FileInputStream) {
        val buf = ByteArray(MAX_IP_PACKET)
        var lastHb = System.currentTimeMillis()

        while (coroutineContext.isActive && isConnected) {
            try {
                val n = tunInput.read(buf)
                if (n <= 0) {
                    if (n < 0) break  // TUN fd 关闭
                    // n == 0: 非阻塞空读
                    delay(1)
                    val now = System.currentTimeMillis()
                    if (now - lastHb >= HB_INTERVAL_MS) {
                        sendHeartbeat(HB_PING)
                        lastHb = now
                    }
                    continue
                }

                // 发送 IP 包到 RK3588
                val packet = DatagramPacket(buf, n, peerAddr)
                udpSocket?.send(packet)
                lastHb = System.currentTimeMillis()
            } catch (e: Exception) {
                if (coroutineContext.isActive) {
                    Log.e(TAG, "TUN→UDP 异常", e)
                }
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
                udpSocket?.receive(packet)  // 阻塞直到收到包或超时

                val n = packet.length
                if (n <= 0) continue
                lastPkt = System.currentTimeMillis()

                // 心跳处理
                if (n == 1) {
                    when (buf[0]) {
                        HB_PING -> sendHeartbeat(HB_PONG)
                        HB_PONG -> { /* 对端回复，仅重置计时器 */ }
                    }
                    continue
                }

                // 数据包: 写入 TUN
                if (n <= MAX_IP_PACKET) {
                    tunOutput.write(buf, 0, n)
                }
            } catch (e: SocketTimeoutException) {
                // 正常超时，检查链路是否断开
                val now = System.currentTimeMillis()
                if (now - lastPkt > HB_TIMEOUT_MS && isConnected) {
                    Log.w(TAG, "对端超时 ${(now - lastPkt) / 1000}s，断开")
                    isConnected = false
                    onLinkStateChange?.invoke(LinkState.Disconnected)
                    break
                }
                continue
            } catch (e: Exception) {
                if (coroutineContext.isActive) {
                    Log.e(TAG, "UDP→TUN 异常", e)
                }
                break
            }
        }
        isConnected = false
        onLinkStateChange?.invoke(LinkState.Disconnected)
        Log.i(TAG, "UDP→TUN 退出")
    }

    /* ── 心跳 ────────────────────────────────────────── */

    private fun sendHeartbeat(byte: Byte) {
        try {
            val data = byteArrayOf(byte)
            val pkt = DatagramPacket(data, 1, peerAddr)
            udpSocket?.send(pkt)
        } catch (_: Exception) { /* 忽略发送失败，下轮重试 */ }
    }

    /* ── 断开 ────────────────────────────────────────── */

    fun disconnect() {
        isConnected = false
        onLinkStateChange?.invoke(LinkState.Disconnected)
        try { udpSocket?.close() } catch (_: Exception) {}
        udpSocket = null
    }
}
