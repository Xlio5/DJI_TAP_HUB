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

        /** 当前 VpnService 实例（供 protectSocket 静态调用） */
        @Volatile private var instance: TunNatVpnService? = null

        /** 静态 protect UDP socket，供外部（如 MainActivity 延迟测试）使用 */
        fun protectSocket(socket: java.net.DatagramSocket): Boolean {
            return instance?.protect(socket) ?: false
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
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private val reconnectScope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    override fun onCreate() {
        super.onCreate()
        instance = this
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        Log.i(TAG, "VpnService 启动")

        // 已在运行，忽略重复的启动请求
        // USB 热插拔由 BootReceiver 先停止再启动，不走这里
        if (isStarted) {
            Log.w(TAG, "VpnService 已在运行，忽略重复启动")
            return START_STICKY
        }
        isStarted = true
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
                    updateNotification("已连接 (USB Bulk)")
                }
                com.tunnathub.app.usb.LinkState.Disconnected -> {
                    isReconnectingState.value = true
                    updateNotification("USB 已断开")
                    AppLog.w(TAG, "USB 链路断开，等待设备重新连接...")
                    // 启动重连协程
                    reconnectScope.launch { doReconnect() }
                }
                else -> updateNotification("重连中...")
            }
        }

        // 首次连接
        scope.launch { doReconnect() }

        return START_STICKY
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
     * 尝试一次性连接 USB，失败时注册 USB_DEVICE_ATTACHED 等待设备重新插入
     */
    private suspend fun doReconnect() {
        if (!isStarted || !reconnecting.compareAndSet(false, true)) return
        usbBridge?.disconnect()
        isReconnectingState.value = true

        // 先在主线程注册 USB 监听（防止漏掉插入事件）
        withContext(Dispatchers.Main) {
            unregisterReconnectReceiver()
            val latch = java.util.concurrent.CountDownLatch(1)
            reconnectLatch.set(latch)
            reconnectReceiver = object : BroadcastReceiver() {
                override fun onReceive(ctx: Context, intent: Intent) {
                    if ("android.hardware.usb.action.USB_DEVICE_ATTACHED" == intent.action) {
                        val dev = intent.getParcelableExtra<UsbDevice>(UsbManager.EXTRA_DEVICE)
                        if (dev != null && dev.vendorId == UsbBridge.USB_VID && dev.productId == UsbBridge.USB_PID) {
                            AppLog.i(TAG, "收到 V3s 插入广播")
                            latch.countDown()
                        }
                    }
                }
            }
            registerReceiver(reconnectReceiver, IntentFilter("android.hardware.usb.action.USB_DEVICE_ATTACHED"), Context.RECEIVER_NOT_EXPORTED)
        }

        try {
            var retries = 0
            while (isStarted) {
                retries++
                // 先立即试一次（第一次可能设备已经在线）
                if (retries == 1) {
                    try {
                        updateNotification("USB 连接中...")
                        usbBridge!!.start(scope)
                        AppLog.i(TAG, "USB 首次连接成功")
                        isReconnectingState.value = false
                        return
                    } catch (e: Exception) {
                        AppLog.w(TAG, "USB 未在线: ${e.message}，等待插入...")
                        updateNotification("等待 USB 设备...")
                    }
                }

                // 等待 USB 插入（阻塞 IO 线程，等待硬件事件）
                val latch = reconnectLatch.get()
                if (latch != null) {
                    withContext(Dispatchers.IO) { latch.await() }
                    reconnectLatch.set(java.util.concurrent.CountDownLatch(1))  // 重置
                }
                if (!isStarted) break

                delay(1000)  // 等驱动加载完
                // DJI RC 权限授予有延迟 → 重试多次
                var reconnected = false
                for (attempt in 1..5) {
                    try {
                        updateNotification("重连中... ($retries)")
                        usbBridge?.disconnect()
                        usbBridge!!.start(scope)
                        AppLog.i(TAG, "USB 重连成功 (第${retries}次)")
                        isReconnectingState.value = false
                        reconnected = true
                        break
                    } catch (e: Exception) {
                        AppLog.w(TAG, "USB 重连尝试 $attempt/5 失败: ${e.message}")
                        usbBridge?.disconnect()
                        if (attempt < 5) delay(800)
                    }
                }
                if (reconnected) return
                // 5 次都失败 → 重新等广播
            }
        } finally {
            reconnecting.set(false)
            withContext(Dispatchers.Main) { unregisterReconnectReceiver() }
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
        isRunning = false
        usbBridge?.disconnect()
        usbBridge = null

        try {
            tunFd?.close()
        } catch (_: Exception) {}
        tunFd = null

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
