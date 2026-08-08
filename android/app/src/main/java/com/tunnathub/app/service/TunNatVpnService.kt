/**
 * TunNatVpnService.kt — Android VpnService 实现
 *
 * 核心职责:
 *   1. 创建 TUN 接口（VpnService.Builder.establish()）
 *   2. 配置路由：仅捕获局域网流量（192.168.88.0/24）
 *   3. 启动 USB Bridge 双协程转发
 *   4. 前台服务保活
 *
 * TUN 参数:
 *   Android IP: 10.0.0.2/24
 *   Route:      192.168.88.0/24
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
import com.tunnathub.app.usb.UsbBridge
import com.tunnathub.app.util.AppLog
import kotlinx.coroutines.*
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

        /** VPN 服务进程是否存活 (与 isRunning 区分: 服务在但 USB 断开时 isRunning=false) */
        @Volatile var isStartedForUi: Boolean = false
            private set

        /** 当前 VpnService 实例（供 protectSocket 静态调用） */
        @Volatile private var instance: TunNatVpnService? = null

        /** 静态 protect UDP socket，供外部（如 MainActivity 延迟测试）使用 */
        fun protectSocket(socket: java.net.DatagramSocket): Boolean {
            return instance?.protect(socket) ?: false
        }

        /** 受保护的 UDP 端口映射 (port → DatagramSocket) */
        private val protectedPorts = java.util.concurrent.ConcurrentHashMap<Int, java.net.DatagramSocket>()
        val protectedPortsState = mutableStateOf(emptyList<Int>())

        /** 保护一个 UDP 端口：创建 socket + bind + protect，保持存活让内核路由包 */
        fun protectPort(port: Int): Boolean {
            return openProtectedPort(port) != null
        }

        /** 打开(或复用)一个受保护的 UDP socket 并返回它, 供调用方 receive()
         * 绑定 TUN 地址(10.0.0.2) 的指定端口, 标记 protect 绕过 VPN 隧道,
         * 让内核把从 TUN 接口入站的该端口 UDP 包投递到该 socket。
         */
        fun openProtectedPort(port: Int): java.net.DatagramSocket? {
            val inst = instance ?: return null
            protectedPorts[port]?.let { return it }   // 已存在则复用
            return try {
                val socket = java.net.DatagramSocket(null)
                socket.reuseAddress = true
                socket.bind(java.net.InetSocketAddress(TUN_ADDRESS, port))
                inst.protect(socket)
                protectedPorts[port] = socket
                protectedPortsState.value = protectedPorts.keys().toList().sorted()
                AppLog.i(TAG, "UDP端口保护: $port")
                socket
            } catch (e: Exception) {
                AppLog.e(TAG, "UDP端口保护失败: $port — ${e.message}")
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

        // TUN 配置 (默认值, 高级设置可覆盖)
        private const val TUN_ADDRESS = "10.0.0.2"
        private const val TUN_PREFIX = 24
        private const val TUN_MTU = 1400
        private const val TUN_ROUTE = "10.0.0.0"
        private const val TUN_PREFIX_ROUTE = 24
        private const val RECONNECT_DELAY = 1500L  // USB 断开后重连间隔

        // LAN 网段可从 SharedPreferences 覆盖 (高级设置)
        private const val PREFS_NAME = "tun_nat_hub"
        private const val KEY_LAN_SUBNET = "lan_subnet"
        private const val KEY_LAN_PREFIX = "lan_prefix"
        private const val DEFAULT_LAN_SUBNET = "192.168.88.0"
        private const val DEFAULT_LAN_PREFIX = 24
    }

    private var tunFd: ParcelFileDescriptor? = null
    private var usbBridge: UsbBridge? = null
    private var isStarted = false
    private var scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private var reconnectScope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    override fun onCreate() {
        super.onCreate()
        instance = this
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        Log.i(TAG, "VpnService 启动")

        // isStarted 残留 true (上次停止不彻底) 时强制重启:
        // 否则 USB Bridge 不启动, 导致"开多次 App 才能连上"
        if (isStarted) {
            Log.w(TAG, "VpnService 残留, 强制重启")
            stopVpn()   // 停掉旧的 (TUN + USB + isStarted 复位)
            // 重新初始化 USB Bridge (onDestroy 可能没跑, 这里补)
            usbBridge?.disconnect()
            usbBridge = null
        }
        isStarted = true
        isStartedForUi = true
        isRunning = true

        // 前台服务
        startForeground(NOTIFICATION_ID, buildNotification("正在启动..."))

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
        usbBridge = UsbBridge(this, tunFd!!)
        // 无限重连 — USB 断开自动恢复，等 USB_DEVICE_ATTACHED 广播
        usbBridge!!.onLinkStateChange = { state ->
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
        AppLog.i(TAG, "建立 VPN: TUN=$TUN_ADDRESS/$TUN_PREFIX, Route=$lanSubnet/$lanPrefix")

        val builder = Builder()
            .setSession(getString(R.string.vpn_service_name))
            .setMtu(TUN_MTU)
            .addAddress(TUN_ADDRESS, TUN_PREFIX)
            .addRoute(lanSubnet, lanPrefix)
            .addRoute(TUN_ROUTE, TUN_PREFIX_ROUTE)
            .setBlocking(true)
            .allowBypass()

        return builder.establish()
            ?: throw IllegalStateException("VpnService.Builder.establish() 返回 null")
    }

    private var reconnectReceiver: BroadcastReceiver? = null
    private val reconnectLatch = java.util.concurrent.atomic.AtomicReference<java.util.concurrent.CountDownLatch?>(null)
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
                    usbBridge!!.start(scope)
                    AppLog.i(TAG, "USB 连接成功 (第${retries}次)")
                    isReconnectingState.value = false
                    // Connected 回调已设 isRunning=true, 这里兜底
                    isRunning = true
                    return
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
        reconnectLatch.set(null)
    }

    /**
     * 停止 VPN
     */
    private fun stopVpn() {
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
