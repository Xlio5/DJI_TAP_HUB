/**
 * TunNatVpnService.kt — Android VpnService 实现
 *
 * 核心职责:
 *   1. 创建 TUN 接口（VpnService.Builder.establish()）
 *   2. 配置路由：仅捕获局域网流量（192.168.144.0/24）
 *   3. 启动 USB Bridge 双协程转发
 *   4. 前台服务保活
 *
 * TUN 参数:
 *   Android IP: 192.168.144.11/24 (手机在局域网里的真 IP)
 *   Route:      192.168.144.0/24
 *   MTU:        1400
 */

package com.tunnathub.app.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.hardware.usb.UsbDevice
import android.hardware.usb.UsbManager
import android.net.VpnService
import android.os.Build
import android.os.ParcelFileDescriptor
import android.util.Log
import androidx.compose.runtime.mutableStateOf
import com.tunnathub.app.MainActivity
import com.tunnathub.app.R
import com.tunnathub.app.RcMsg
import com.tunnathub.app.rc.AdbGetEventReader
import com.tunnathub.app.rc.Port40007RcReader
import com.tunnathub.app.rc.RcFusionRuntime
import com.tunnathub.app.rc.RcMsgTransport
import com.tunnathub.app.rc.RcSourceStats
import com.tunnathub.app.rc.ShizukuGetEventReader
import com.tunnathub.app.rc.Tcp40007PacketSource
import com.tunnathub.app.usb.UsbBridge
import com.tunnathub.app.util.AppLog
import com.tunnathub.app.video.VpnNetworkBinder
import kotlinx.coroutines.*
import rikka.shizuku.Shizuku
import java.net.DatagramSocket
import java.net.InetSocketAddress
import java.util.concurrent.ConcurrentHashMap

class TunNatVpnService : VpnService() {

    companion object {
        private const val TAG = "TunNatVpnService"
        private const val NOTIFICATION_ID = 1001
        private const val CHANNEL_ID = "tun_nat_hub_vpn"

        /** 供 MainActivity 观察 VPN 运行状态 */
        val isRunningState = mutableStateOf(false)
        var isRunning: Boolean
            get() = isRunningState.value
            private set(value) { isRunningState.value = value }

        /** 是否正在重连 USB */
        val isReconnectingState = mutableStateOf(false)

        /** 服务侧融合 RC 最新数据：Activity 仅观察显示, 采集/发布不依赖 Activity 生命周期。 */
        val fusedRcDataState = mutableStateOf<RcMsg.Data?>(null)

        /** 服务侧 RC 双源实时到达速率 (getevent / 40007)，供遥控页分别显示。 */
        val fusedRcSourceStatsState = mutableStateOf(RcSourceStats())

        /** Shizuku 授权成功后置位, 监视循环检测后重建 RC 融合 → getevent reader 切到 Shizuku。 */
        @Volatile var rcFusionRestartRequested = false

        @JvmStatic
        fun requestRcFusionRestart() {
            rcFusionRestartRequested = true
        }

        /**
         * 强制重建 VPN 标志 (MainActivity 网段变更/手动重连时设置)。
         * onStartCommand 看到此标志时强制 stopVpn+重建, 绕过"直接复用"逻辑,
         * 使新的 lan_subnet 路由生效 (否则复用不重建, 旧路由残留)。
         */
        @Volatile var forceRestartRequested = false

        /** VPN 服务进程是否存活 (与 isRunning 区分: 服务在但 USB 断开时 isRunning=false) */
        @Volatile var isStartedForUi: Boolean = false
            private set

        /** 当前 VpnService 实例（供 protectSocket 静态调用） */
        @Volatile private var instance: TunNatVpnService? = null

        @JvmStatic
        fun isVpnRunningForJava(): Boolean = isRunning

        @JvmStatic
        fun bindProcessToVpnNetwork(): Boolean {
            val ctx = instance?.applicationContext ?: return false
            return VpnNetworkBinder.bindProcessToVpn(ctx)
        }

        /** 把 UDP socket 显式绑定到 VPN network (走 tun0, 避免 uid 规则覆盖走 wlan0)
         *  CrsfBridge.sendSocket 调用, 确保发包到 144.66 (V3s) 走隧道 */
        @JvmStatic
        fun bindSocketToVpn(socket: java.net.DatagramSocket): Boolean {
            val inst = instance ?: return false
            val ctx = inst.applicationContext
            val cm = ctx.getSystemService(android.content.Context.CONNECTIVITY_SERVICE) as android.net.ConnectivityManager
            val vpnNet = cm.allNetworks.firstOrNull { net ->
                cm.getNetworkCapabilities(net)?.hasTransport(android.net.NetworkCapabilities.TRANSPORT_VPN) == true
            } ?: return false
            return try {
                // Network.bindSocket() API 23+, 比 bindSocketToNetwork(API30) 兼容更广 (minSdk=26)
                vpnNet.bindSocket(socket)
                AppLog.i(TAG, "bindSocketToVpn vpn=$vpnNet ok=true")
                true
            } catch (e: Exception) {
                AppLog.w(TAG, "bindSocketToVpn err: $e")
                false
            }
        }

        @JvmStatic
        fun clearProcessNetworkBinding() {
            val ctx = instance?.applicationContext ?: return
            VpnNetworkBinder.clearProcessBinding(ctx)
        }

        /** 静态 protect UDP socket，供外部（如 MainActivity 延迟测试）使用 */
        fun protectSocket(socket: java.net.DatagramSocket): Boolean {
            return instance?.protect(socket) ?: false
        }

        /** 受保护的 UDP 端口映射 (port → DatagramSocket), 绑定手机局域网 IP (144.11) */
        private val protectedPorts = java.util.concurrent.ConcurrentHashMap<Int, java.net.DatagramSocket>()
        val protectedPortsState = mutableStateOf(emptyList<Int>())

        /** 保护一个 UDP 端口：创建 socket + bind + protect，保持存活让内核路由包 */
        fun protectPort(port: Int): Boolean {
            return openProtectedPort(port) != null
        }

        /** 当前生效的手机 LAN 身份 IP (establishVpn 时从 lanSubnet 推导, 默认 192.168.144.11)。
         * 局域网设备 ping/访问这个 IP = 直达手机 (V3s DNAT 到 10.0.0.2 主地址)。
         * 注意: 这是副地址 (LAN 身份), 收包 socket 绑主地址 10.0.0.2 (openProtectedPort)。 */
        @Volatile
        var currentLanAddr: String = "192.168.144.11"
            private set

        /**
         * 打开(或复用)一个受保护的 UDP socket 并返回它, 供调用方 receive()。
         * 绑定手机局域网 IP (144.11), 标记 protect 绕过 VPN 隧道,
         * 让内核把从 TUN 接口入站的该端口 IPv4 UDP 包投递到该 socket。
         *
         * ⚠️ 关键 (Android VpnService 限制): 只能绑定具体 TUN 子网 IP (144.11),
         * 不能绑 0.0.0.0 通配 — 通配会创建 IPv6 双栈 socket (udp6), 收不到经 tun0
         * 进入的 IPv4 包 (实测 InDatagrams 涨但 socket rx_queue=0)。
         */
        fun openProtectedPort(port: Int): java.net.DatagramSocket? {
            // 绑手机主地址 10.0.0.2 (控制面 rcmsg/crsfbr 都发主地址, V3s DNAT 到主地址)。
            // Android VpnService 只对主地址投递隧道包, 副地址(144.11)收不到。
            return openProtectedPortOn(port, INTERNAL_FWD_ADDR, protectedPorts)
        }

        /** 打开内部转发地址 (10.0.0.2) 的受保护 UDP socket。
         * 电脑发 144.11:port 的包被 V3s DNAT 到 10.0.0.2:port, 由此 socket 接收。 */
        fun openInternalPort(port: Int): java.net.DatagramSocket? {
            return openProtectedPortOn(port, INTERNAL_FWD_ADDR, protectedPorts)
        }

        /** 打开绑定 VPN 网络的 UDP socket (非 protect)。
         * 区别: protect socket 只收隧道内部源的包 (V3s 的 rcmsg), 不收电脑经 V3s 转发的包
         * (源 144.88, Android 不投递给 protect socket)。bindSocketToVpn 让 socket 在 VPN 网络内,
         * 电脑转发的包 (V3s DNAT 到 10.0.0.2:port) 才能投递进来。
         * 返回 null 表示无 VPN 网络。 */
        fun openVpnBoundPort(port: Int): java.net.DatagramSocket? {
            val inst = instance ?: return null
            return try {
                // DatagramChannel INET 强制纯 IPv4 (v4-mapped 收不到隧道包)
                val channel = java.nio.channels.DatagramChannel.open(java.net.StandardProtocolFamily.INET)
                val socket = channel.socket()
                socket.reuseAddress = true
                socket.bind(java.net.InetSocketAddress(INTERNAL_FWD_ADDR, port))
                // bindSocketToVpn 而非 protect: socket 留在 VPN 网络内, 收电脑转发的包
                val bindOk = bindSocketToVpn(socket)
                AppLog.i(TAG, "UDP VPN绑定: $INTERNAL_FWD_ADDR:$port bindVpn=$bindOk")
                socket
            } catch (e: Exception) {
                AppLog.e(TAG, "UDP VPN绑定失败: $port — ${e.message}")
                null
            }
        }

        private fun openProtectedPortOn(
            port: Int,
            bindAddr: String,
            registry: ConcurrentHashMap<Int, java.net.DatagramSocket>
        ): java.net.DatagramSocket? {
            val inst = instance ?: return null
            // 复用前检查 socket 有效性: 若已被关闭 (fd 释放但 inode 残留, 孤儿 socket),
            // 必须重建 — 否则 receive() 永远收不到数据 (摇杆/心跳丢失)。
            registry[port]?.let { existing ->
                if (existing.isClosed || !existing.isBound) {
                    AppLog.w(TAG, "UDP端口保护: $port socket 失效, 重建")
                    try { existing.close() } catch (_: Exception) {}
                    registry.remove(port)
                } else {
                    return existing   // 有效, 复用
                }
            }
            return try {
                // 用 DatagramChannel.open(INET) 强制创建纯 IPv4 socket (AF_INET)。
                // 若用 new DatagramSocket(null) + bind, 系统启用 IPv6 时会被提升为
                // v4-mapped 双栈 socket (内核显示 ::ffff:144.11), 实测收不到经
                // tun0 进入的 IPv4 UDP 包 (InDatagrams 涨但 socket rx_queue=0) —
                // Android VpnService 对 v4-mapped 的隧道入站投递有 bug。
                val channel = java.nio.channels.DatagramChannel.open(
                    java.net.StandardProtocolFamily.INET)
                val socket = channel.socket()
                socket.reuseAddress = true
                // 绑定手机局域网 IP (144.11): 局域网设备发到该地址:port 的包才能投递进来
                socket.bind(java.net.InetSocketAddress(bindAddr, port))
                val protectOk = inst.protect(socket)
                registry[port] = socket
                protectedPortsState.value = protectedPorts.keys().toList().sorted()
                AppLog.i(TAG, "UDP端口保护: $bindAddr:$port protect=$protectOk bound=${socket.isBound}")
                socket
            } catch (e: Exception) {
                AppLog.e(TAG, "UDP端口保护失败: $bindAddr:$port — ${e.message}")
                null
            }
        }

        /** 释放一个受保护的 UDP 端口 */
        fun releasePort(port: Int) {
            protectedPorts.remove(port)?.let {
                try { it.close() } catch (_: Exception) {}
                protectedPortsState.value = protectedPorts.keys().toList().sorted()
                AppLog.i(TAG, "UDP端口释放: $port")
            }
        }

        /** 释放所有受保护的端口 */
        fun releaseAllPorts() {
            protectedPorts.values.forEach { try { it.close() } catch (_: Exception) {} }
            protectedPorts.clear()
            protectedPortsState.value = emptyList()
        }

        // TUN 配置 (手机地址 = 局域网 x.x.x.11, 从 lanSubnet 推导)
        private const val TUN_PREFIX = 24
        private const val TUN_MTU = 1400
        private const val RECONNECT_DELAY = 1500L  // USB 断开后重连间隔
        private const val SERVICE_KEEPALIVE_INTERVAL_MS = 15_000L
        private const val USB_WATCHDOG_INTERVAL_MS = 2_000L

        // LAN 网段可从 SharedPreferences 覆盖 (高级设置)
        private const val PREFS_NAME = "tun_nat_hub"
        private const val KEY_LAN_SUBNET = "lan_subnet"
        private const val KEY_LAN_PREFIX = "lan_prefix"
        private const val DEFAULT_LAN_SUBNET = "192.168.144.0"
        private const val DEFAULT_LAN_PREFIX = 24

        /** 手机在局域网里的 IP 尾号 (V3s = 144.66, 手机 = 144.11, 固定预留不撞 DHCP) */
        private const val PHONE_IP_OCTET = 11

        /** 内部转发地址: V3s 把电脑发来的 144.11 包 DNAT 到此地址 (绕开 V3s 老内核 INPUT 问题) */
        private const val INTERNAL_FWD_ADDR = "10.0.0.2"
    }

    private var tunFd: ParcelFileDescriptor? = null
    private var usbBridge: UsbBridge? = null
    @Volatile private var isStarted = false   // M-05: 主线程写/IO线程读, 需可见性
    // C-01: 主线程重建 (stopVpn), IO 线程读 (onLinkStateChange 触发 reconnectScope.launch),
    // 无 @Volatile 可能读到已取消的旧 scope → 重连静默失败
    @Volatile private var scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    @Volatile private var reconnectScope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private val keepAliveThreadsRunning = java.util.concurrent.atomic.AtomicBoolean(false)
    @Volatile private var serviceKeepAliveThread: Thread? = null
    @Volatile private var usbWatchdogThread: Thread? = null
    @Volatile private var rcFusionJob: Job? = null
    @Volatile private var rcFusionRuntime: RcFusionRuntime? = null

    override fun onCreate() {
        super.onCreate()
        instance = this
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        Log.i(TAG, "VpnService 启动")

        // 修复: 退出 app 时 VPN 服务 (TunNatVpnService) 仍在后台运行, USB 隧道也还连着。
        // 再进 app 时不应强制重启 VPN (stopVpn 会关 TUN+USB+受保护端口 incl. 65530 摇杆 socket,
        // 重建后 RC effect 重新建 socket, 时序/投递易出问题 → 摇杆丢失)。
        // 正确逻辑: 服务已启动且隧道健康 (isStarted=true, USB 连通 isRunning=true) → 直接复用, 不重建。
        // 服务已启动但隧道断了 → 服务内部 doReconnect 会后台自动重连, 也不需强制重启。
        // 只有服务确实未初始化 (isStarted=false) 才走完整启动流程。
        if (isStarted) {
            // 强制重建标志 (网段变更/手动重连): 必须重建 VPN 让新路由生效。
            if (forceRestartRequested) {
                forceRestartRequested = false
                Log.w(TAG, "强制重建 VPN (网段变更/手动重连)")
                stopVpn()
                usbBridge?.disconnect()
                usbBridge = null
            } else if (isRunning) {
                // 服务已在跑: 隧道已连通则直接复用, 不打断 (保留受保护端口/摇杆 socket)。
                Log.i(TAG, "VPN 服务已在运行, 直接复用 (不重启, 保留摇杆/受保护端口)")
                isStartedForUi = true
                return START_STICKY
            } else {
                // 服务在但隧道断了: 不强制重启, 服务内部 doReconnect 会重连。
                // 再补一次重连触发，防止重连循环因异常/竞态退出后无人唤醒。
                Log.w(TAG, "VPN 服务在但隧道未连, 交由 doReconnect 重连 (不强制重启)")
                isStartedForUi = true
                reconnectScope.launch { doReconnect() }
                return START_STICKY
            }
        }
        isStarted = true
        isStartedForUi = true
        isRunning = false

        // 前台服务
        startForeground(NOTIFICATION_ID, buildNotification("正在启动..."))
        startKeepAliveThreads()

        // 建立 TUN 接口
        try {
            tunFd = establishVpn()
            Log.i(TAG, "TUN 接口已建立")
            AppLog.i(TAG, "TUN 接口已建立")
        } catch (e: Exception) {
            Log.e(TAG, "无法建立 TUN", e)
            stopSelf()
            return START_NOT_STICKY
        }

        // 启动 USB Bridge（带自动重试 + 回调更新通知）
        val fd = tunFd ?: return START_NOT_STICKY   // L-04: 避免 !!
        usbBridge = UsbBridge(this, fd)
        // 无限重连 — USB 断开自动恢复，等 USB_DEVICE_ATTACHED 广播
        usbBridge?.onLinkStateChange = { state ->
            when (state) {
                com.tunnathub.app.usb.LinkState.Connected -> {
                    isReconnectingState.value = false
                    // 状态联动: USB 转发活跃 → isRunning=true (UI 显示连接/运行)
                    isRunning = true
                    updateNotification("已连接 (USB Bulk)")
                }
                com.tunnathub.app.usb.LinkState.Disconnected -> {
                    isReconnectingState.value = true
                    // 状态联动: USB 转发断开 → isRunning=false (UI 显示"连接"可点击重连)
                    // 服务进程保持存活, 重连协程继续后台静默恢复
                    isRunning = false
                    updateNotification("USB 已断开")
                    AppLog.w(TAG, "USB 链路断开，等待设备重新连接...")
                    // 启动重连协程
                    reconnectScope.launch { doReconnect() }
                }
                else -> updateNotification("重连中...")
            }
        }

        // 注册 USB 拔出广播: 收到 DETACHED → 触发重连 (不停止服务)
        registerUsbDetachReceiver()
        startRcFusionRuntime()

        // 首次连接
        scope.launch { doReconnect() }

        return START_STICKY
    }

    /**
     * 注册 ACTION_USB_DEVICE_DETACHED 广播。
     * 修复: USB 拔出时 usbToTunLoop 阻塞在 bulkTransfer 上检测不到断开,
     * 这里用 Android 官方广播作为断开信号 → 触发 doReconnect 轮询重连。
     */
    private fun registerUsbDetachReceiver() {
        unregisterReconnectReceiver()  // 先注销旧的, 避免重复注册
        reconnectReceiver = object : BroadcastReceiver() {
            override fun onReceive(context: Context, intent: Intent) {
                val action = intent.action ?: return
                if (action == android.hardware.usb.UsbManager.ACTION_USB_DEVICE_DETACHED) {
                    val device = intent.getParcelableExtra<android.hardware.usb.UsbDevice>(
                        android.hardware.usb.UsbManager.EXTRA_DEVICE)
                    if (device != null && device.vendorId == com.tunnathub.app.usb.UsbBridge.USB_VID &&
                        device.productId == com.tunnathub.app.usb.UsbBridge.USB_PID) {
                        Log.w(TAG, "USB 拔出广播, 触发重连")
                        AppLog.w(TAG, "USB 拔出广播, 触发重连")
                        isRunning = false
                        if (isStarted) reconnectScope.launch { doReconnect() }
                    }
                }
            }
        }
        try {
            registerReceiver(reconnectReceiver, IntentFilter(android.hardware.usb.UsbManager.ACTION_USB_DEVICE_DETACHED),
                Context.RECEIVER_NOT_EXPORTED)
        } catch (e: Exception) {
            Log.e(TAG, "注册 USB 拔出广播失败: ${e.message}")
        }
    }

    override fun onDestroy() {
        Log.i(TAG, "VpnService 销毁")
        stopKeepAliveThreads()
        stopRcFusionRuntime()
        scope.cancel()
        reconnectScope.cancel()
        unregisterReconnectReceiver()
        stopVpn()
        super.onDestroy()
    }

    /**
     * 使用 VpnService.Builder 建立 TUN 接口
     */
    private fun establishVpn(): ParcelFileDescriptor {
        // 从 SharedPreferences 读取用户自定义 LAN 网段 (高级设置)
        val prefs = getSharedPreferences(PREFS_NAME, MODE_PRIVATE)
        val lanSubnet = prefs.getString(KEY_LAN_SUBNET, DEFAULT_LAN_SUBNET) ?: DEFAULT_LAN_SUBNET
        val lanPrefix = prefs.getInt(KEY_LAN_PREFIX, DEFAULT_LAN_PREFIX)
        // 手机在局域网里的 IP: 取 lanSubnet 网段的 x.x.x.11 (如 192.168.144.0 → 192.168.144.11)。
        // 从配置推导而非硬编码, 网段变更 (88→144) 时手机 IP 自动跟随。V3s = x.x.x.66。
        val phoneIp = if (lanSubnet.contains('.')) {
            lanSubnet.substringBeforeLast('.') + ".$PHONE_IP_OCTET"
        } else "${DEFAULT_LAN_SUBNET.substringBeforeLast('.')}.$PHONE_IP_OCTET"
        currentLanAddr = phoneIp   // 供 openProtectedPort 绑定用
        AppLog.i(TAG, "建立 VPN: 手机IP=$phoneIp/$lanPrefix, Route=$lanSubnet/$lanPrefix")

        val builder = Builder()
            .setSession(getString(R.string.vpn_service_name))
            .setMtu(TUN_MTU)
            // 主地址 = 10.0.0.2 (内部转发地址): Android VpnService 只对主地址投递
            // protect 隧道包。V3s 把电脑发来的 144.11 包 DNAT 到这里 (绕开 V3s
            // 老内核把 144.11 当本地 INPUT 的问题)。
            .addAddress(INTERNAL_FWD_ADDR, 24)
            // 副地址 = 手机局域网真 IP 144.11 (LAN 身份, 电脑可见)
            .addAddress(phoneIp, lanPrefix)
            .addRoute(lanSubnet, lanPrefix)
            .setBlocking(true)
            // 移除 allowBypass: 它导致 CrsfBridge socket 走 wlan0 绕过 VPN,
            // 使 CRSF 命令到不了 V3s bridge。移除后所有流量(含 CRSF)走 tun0→USB→V3s。
            // 视频 RTSP (192.168.144.31) 在 lanSubnet 路由内, 走 tun0→USB→V3s→DNAT→摄像头。
            //.allowBypass()

        return builder.establish()
            ?: throw IllegalStateException("VpnService.Builder.establish() 返回 null")
    }

    private var reconnectReceiver: BroadcastReceiver? = null
    private val reconnecting = java.util.concurrent.atomic.AtomicBoolean(false)

    /**
     * 尝试连接 USB。失败后轮询重试（不依赖 USB 插入广播，
     * 设备一直插着也能重连，解决"开多次 App 才连上"的问题）。
     */
    private suspend fun doReconnect() {
        if (!isStarted || !reconnecting.compareAndSet(false, true)) return
        usbBridge?.disconnect()
        isReconnectingState.value = true
        // 连接尚未建立成功, 状态应为 false (H1: isRunning 反映真实连接状态)
        isRunning = false

        try {
            var retries = 0
            while (isStarted) {
                retries++
                try {
                    updateNotification("USB 连接中... ($retries)")
                    // H-02: 局部变量安全检查, 避免与 stopVpn() 置 null 竞态 NPE
                    val bridge = usbBridge ?: break
                    bridge.start(scope)
                    AppLog.w(TAG, "USB 转发循环已退出 (第${retries}次), 继续重连")
                    isReconnectingState.value = true
                    isRunning = false
                } catch (e: kotlinx.coroutines.CancellationException) {
                    throw e   // H-01: 协程取消必须传播, 避免 isRunning 被错误覆写
                } catch (e: Exception) {
                    AppLog.w(TAG, "USB 连接失败 (第${retries}次): ${e.message}")
                    updateNotification("USB 重连中... ($retries)")
                    // H1: 连接失败 → isRunning 保持 false (UI 显示"连接"可重连)
                    isRunning = false
                }
                // 轮询重试: 设备一直插着也能重连, 不依赖插入广播
                delay(RECONNECT_DELAY)
            }
        } finally {
            reconnecting.set(false)
        }
    }

    private fun unregisterReconnectReceiver() {
        reconnectReceiver?.let { try { unregisterReceiver(it) } catch (_: Exception) {} }
        reconnectReceiver = null
    }

    /**
     * 双线程保活:
     * 1) 服务心跳线程: 周期性刷新前台通知, 避免长时间无 UI 交互时状态沉默。
     * 2) USB 巡检线程: 发现服务仍在但 USB bridge 未连接时, 兜底唤醒重连流程。
     */
    private fun startKeepAliveThreads() {
        if (!keepAliveThreadsRunning.compareAndSet(false, true)) return

        serviceKeepAliveThread = Thread({
            AppLog.i(TAG, "服务保活线程启动")
            while (keepAliveThreadsRunning.get()) {
                try {
                    val status = when {
                        isRunning -> "已连接 (保活中)"
                        isReconnectingState.value -> "USB 重连中..."
                        isStarted -> "等待 USB 连接..."
                        else -> "已停止"
                    }
                    updateNotification(status)
                    Thread.sleep(SERVICE_KEEPALIVE_INTERVAL_MS)
                } catch (e: InterruptedException) {
                    break
                } catch (e: Exception) {
                    Log.w(TAG, "服务保活线程异常: ${e.message}")
                    try { Thread.sleep(SERVICE_KEEPALIVE_INTERVAL_MS) } catch (_: InterruptedException) { break }
                }
            }
            AppLog.i(TAG, "服务保活线程退出")
        }, "TunNatHub-ServiceKeepAlive").apply {
            isDaemon = true
            start()
        }

        usbWatchdogThread = Thread({
            AppLog.i(TAG, "USB 巡检线程启动")
            while (keepAliveThreadsRunning.get()) {
                try {
                    if (isStarted) {
                        val bridge = usbBridge
                        val shouldKickReconnect = bridge == null || !bridge.isConnected
                        if (shouldKickReconnect && !reconnecting.get()) {
                            AppLog.w(TAG, "USB 巡检发现链路未连接, 触发重连")
                            reconnectScope.launch { doReconnect() }
                        }
                    }
                    Thread.sleep(USB_WATCHDOG_INTERVAL_MS)
                } catch (e: InterruptedException) {
                    break
                } catch (e: Exception) {
                    Log.w(TAG, "USB 巡检线程异常: ${e.message}")
                    try { Thread.sleep(USB_WATCHDOG_INTERVAL_MS) } catch (_: InterruptedException) { break }
                }
            }
            AppLog.i(TAG, "USB 巡检线程退出")
        }, "TunNatHub-UsbWatchdog").apply {
            isDaemon = true
            start()
        }
    }

    private fun stopKeepAliveThreads() {
        keepAliveThreadsRunning.set(false)
        serviceKeepAliveThread?.interrupt()
        usbWatchdogThread?.interrupt()
        serviceKeepAliveThread = null
        usbWatchdogThread = null
    }

    /**
     * Android 侧 RC 融合输入放在 VpnService 内运行。
     * 这样用户划掉 Activity 后, adb getevent + 40007 仍由前台 VPN 服务持续采集,
     * 并按固定周期发布 RCM1 给 V3s 输出链路。
     */
    private fun startRcFusionRuntime() {
        if (rcFusionJob != null) return
        rcFusionJob = scope.launch {
            while (isStarted && isActive) {
                var socket: DatagramSocket? = null
                try {
                    socket = DatagramSocket()
                    if (!bindSocketToVpn(socket)) {
                        socket.close()
                        throw IllegalStateException("RC 融合 UDP socket 绑定 VPN 网络失败")
                    }
                    val transport = RcMsgTransport(socket, onLocalData = { data ->
                        fusedRcDataState.value = data
                    })
                    val runtime = RcFusionRuntime(
                        geteventReaderFactory = { onSample ->
                            // getevent 高频源: Shizuku App 装着 → 始终用 Shizuku reader (内部自检未就绪重试,
                            // 等绑定/授权就绪自动恢复); 未装 Shizuku → adb 回退 (通常读不到, 仅尝试)。
                            val shizukuInstalled = try {
                                applicationContext.packageManager
                                    .getPackageInfo("moe.shizuku.privileged.api", 0) != null
                            } catch (_: Exception) {
                                false
                            }
                            if (shizukuInstalled) {
                                AppLog.i("RcFusion", "getevent reader: Shizuku")
                                ShizukuGetEventReader(onSample)
                            } else {
                                AppLog.i("RcFusion", "getevent reader: adb(回退)")
                                AdbGetEventReader(context = applicationContext, onSample = onSample)
                            }
                        },
                        port40007ReaderFactory = { onSample ->
                            Port40007RcReader(Tcp40007PacketSource(), onSample)
                        },
                        transport = transport,
                        onError = { source, error ->
                            AppLog.w("RcFusion", "$source 输入停止: ${error.message}")
                        },
                        onSourceStats = { fusedRcSourceStatsState.value = it }
                    )
                    rcFusionRuntime = runtime
                    runtime.start()
                    AppLog.i("RcFusion", "服务侧 RC 融合输入已启动")
                    // 内层监视循环: runtime 内部 publish 连续失败自判死亡 (isHealthy=false) → 跳出重建整个融合。
                    // 修复: 之前 publish 协程异常会静默终止, 外层检测不到 → 摇杆停在最后值, 只能重启服务恢复。
                    while (isStarted && isActive && runtime.isHealthy) {
                        // Shizuku 授权成功后重建: getevent reader 从 adb 回退切到 Shizuku
                        if (rcFusionRestartRequested) {
                            rcFusionRestartRequested = false
                            break
                        }
                        delay(1000L)
                    }
                } catch (e: CancellationException) {
                    throw e
                } catch (e: Exception) {
                    AppLog.e("RcFusion", "服务侧 RC 融合启动失败: ${e.message}")
                    socket?.close()
                    delay(1000L)
                } finally {
                    rcFusionRuntime?.close()
                    rcFusionRuntime = null
                }
            }
        }
    }

    private fun stopRcFusionRuntime() {
        rcFusionJob?.cancel()
        rcFusionJob = null
        rcFusionRuntime?.close()
        rcFusionRuntime = null
    }

    /**
     * 停止 VPN
     */
    private fun stopVpn() {
        stopKeepAliveThreads()
        stopRcFusionRuntime()
        isStarted = false
        isStartedForUi = false
        isRunning = false
        usbBridge?.disconnect()
        usbBridge = null

        // 取消旧协程 (TUN→USB / USB→TUN), 避免下次启动时旧协程占着 TUN/USB fd
        scope.cancel()
        scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
        // M2: 同时取消 reconnectScope, 避免残留 doReconnect 的 usbBridge!! NPE
        reconnectScope.cancel()
        reconnectScope = CoroutineScope(Dispatchers.IO + SupervisorJob())

        try {
            tunFd?.close()
        } catch (_: Exception) {}
        tunFd = null

        releaseAllPorts()
        Log.i(TAG, "VPN 已停止")
    }

    // ── 通知管理 ──────────────────────────────────────────────

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                getString(R.string.notification_channel),
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "TUN NAT Hub VPN 状态"
                setShowBadge(false)
            }
            val nm = getSystemService(NotificationManager::class.java)
            nm.createNotificationChannel(channel)
        }
    }

    private fun buildNotification(text: String): Notification {
        val pendingIntent = PendingIntent.getActivity(
            this,
            0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )

        return Notification.Builder(this, CHANNEL_ID)
            .setContentTitle(getString(R.string.vpn_service_name))
            .setContentText(text)
            .setSmallIcon(android.R.drawable.ic_menu_share)  // 用系统图标
            .setContentIntent(pendingIntent)
            .setOngoing(true)
            .build()
    }

    private fun updateNotification(text: String) {
        val nm = getSystemService(NotificationManager::class.java)
        nm.notify(NOTIFICATION_ID, buildNotification(text))
    }
}
