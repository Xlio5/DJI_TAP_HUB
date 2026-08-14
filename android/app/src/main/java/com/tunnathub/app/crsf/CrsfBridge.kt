/**
 * CrsfBridge.kt — V3s crsf-bridge 模式网口 UDP 客户端
 *
 * 与 ubuntu/src/dji_rc.cpp 的 crsf-bridge 模式对应:
 *   V3s 把 UART0 收到的 CRSF 参数帧(0x28+) 转发到 UDP 65532,
 *   App 在此收帧; App 发的 CRSF 命令也经此端口 → V3s → UART0。
 *
 * 网口协议: [magic "CRSF" 4B][CRSF 帧], magic = 0x46534352 little-endian
 *
 * 收发 socket 分离:
 *   - 发包 socket: bind 10.0.0.2 走 VPN 隧道发到 V3s (10.0.0.1) —— 不能 protect (否则走 wlan0)
 *   - 收包 socket: TunNatVpnService.openProtectedPort(65532) —— protect 后内核才把
 *     TUN 接口入站的 65532 UDP 包投递到该 socket (参考 rcmsg 收包方式)
 */
package com.tunnathub.app.crsf

import android.util.Log
import com.tunnathub.app.service.TunNatVpnService
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.InetSocketAddress
import java.util.concurrent.Executors
import java.util.concurrent.atomic.AtomicBoolean

object CrsfBridge {
    private const val TAG = "CrsfBridge"
    const val PORT = 65532
    const val MAGIC = 0x46534352  // "CRSF" little-endian on wire

    @Volatile
    var host: String = "192.168.144.66"
        private set

    private var sendSocket: DatagramSocket? = null
    private var recvSocket: DatagramSocket? = null
    private var rxThread: Thread? = null
    private val running = AtomicBoolean(false)

    /** 后台发送线程池 (sendFrame 可能被主线程调用, 避免 NetworkOnMainThread) */
    private val sendExecutor = Executors.newSingleThreadExecutor()

    /** CRSF 帧接收回调 (App 收 UART0 上行的参数帧/遥测) */
    @Volatile
    var onFrame: ((ByteArray) -> Unit)? = null

    /** 启动 UDP 收线程 + 建立发送 socket */
    fun start(hostAddr: String) {
        stop()
        host = hostAddr
        running.set(true)
        // 进程绑定 VPN 网络: 发包到 10.0.0.1 必须走 tun0, 否则 Android 默认走 wlan0 到不了 V3s
        // (参考 UdpRtspPlayer bindProcessToVpnNetwork; rcmsg 收包用 openProtectedPort 同理需 VPN 上下文)
        TunNatVpnService.bindProcessToVpnNetwork()
        // 发包 socket: bind tun0 IP (10.0.0.2) 走 VPN 隧道到 V3s, 不 protect (否则走 wlan0)
        sendSocket = try {
            DatagramSocket(null).apply {
                bind(InetSocketAddress("10.0.0.2", 0))
            }
        } catch (e: Exception) {
            DatagramSocket()
        }
        // 收包 socket: 必须 openProtectedPort 保护, 内核才投递 TUN 入站 65532 包
        // (参考 MainActivity rcmsg 收包方式; 之前普通 socket 收不到 V3s 上行)
        recvSocket = TunNatVpnService.openProtectedPort(PORT) ?: run {
            try { DatagramSocket(PORT) } catch (e: Exception) { null }
        }
        recvSocket?.soTimeout = 1000
        Log.i(TAG, "socket 创建: VPN建立? ${TunNatVpnService.isRunningState.value} host=$host recv=${recvSocket != null}")
        rxThread = Thread {
            Log.i(TAG, "rxThread 启动, recv=${recvSocket}")
            val buf = ByteArray(4 + 62)
            var timeouts = 0
            while (running.get()) {
                try {
                    val pkt = DatagramPacket(buf, buf.size)
                    recvSocket?.receive(pkt)
                    timeouts = 0
                    dispatch(pkt)
                    // 连续消费: ELRS 响应 ping 时连续发 Device_Info+ELRS_STATUS 多帧,
                    // 内核可能把多个 UDP 包同时排入队列。收到一个后立即非阻塞再收, 避免帧对漏收。
                    while (running.get()) {
                        try {
                            val p2 = DatagramPacket(buf, buf.size)
                            recvSocket?.receive(p2)
                            dispatch(p2)
                        } catch (e: java.net.SocketTimeoutException) {
                            break  // 无更多包, 回到阻塞等待
                        }
                    }
                } catch (e: java.net.SocketTimeoutException) {
                    timeouts++
                    if (timeouts % 10 == 0) Log.d(TAG, "rx 超时 x${timeouts} (无包)")
                    continue
                } catch (e: Exception) {
                    if (running.get()) Log.w(TAG, "rx err: $e")
                }
            }
        }.apply { isDaemon = true; start() }
        Log.i(TAG, "started @ $host:$PORT")
    }

    /** 处理一个收到的 UDP 包: 校验 magic + 剥离前缀 → onFrame */
    private fun dispatch(pkt: DatagramPacket) {
        val hex = pkt.data.copyOfRange(0, pkt.length).take(10).joinToString(" ") { "%02x".format(it) }
        Log.i(TAG, "rx ${pkt.length}B from ${pkt.address?.hostAddress}:${pkt.port} [${hex}]")
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
    }

    /** 发送 CRSF 帧到 V3s (App → UART0), 后台线程执行 */
    fun sendFrame(frame: ByteArray) {
        if (frame.size > 62) return
        val sock = sendSocket ?: return
        val hostAddr = host
        val pkt = ByteArray(4 + frame.size)
        pkt[0] = (MAGIC and 0xFF).toByte()
        pkt[1] = ((MAGIC shr 8) and 0xFF).toByte()
        pkt[2] = ((MAGIC shr 16) and 0xFF).toByte()
        pkt[3] = ((MAGIC shr 24) and 0xFF).toByte()
        frame.copyInto(pkt, 4)
        Log.d(TAG, "sendFrame type=0x${frame[2].toString(16)} to $hostAddr:$PORT pkt=${pkt.take(10).joinToString(" "){ "%02x".format(it) }}")
        try {
            val addr = InetAddress.getByName(hostAddr)
            sendExecutor.execute {
                try {
                    sock.send(DatagramPacket(pkt, pkt.size, addr, PORT))
                    Log.d(TAG, "sendFrame sent OK")
                } catch (e: Exception) {
                    Log.w(TAG, "send err: $e")
                }
            }
        } catch (e: Exception) {
            Log.w(TAG, "dns err: $e")
        }
    }

    fun stop() {
        running.set(false)
        sendSocket?.close()
        sendSocket = null
        // 主动释放 protectedPort, 确保下次 start() 重建收包 socket
        // (否则复用失效 socket → inode 残留孤儿, receive 静默丢帧, Device_Info 偶发丢)
        if (recvSocket != null) TunNatVpnService.releasePort(PORT)
        recvSocket?.close()
        recvSocket = null
        rxThread?.join(2000)
        rxThread = null
    }
}
