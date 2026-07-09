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
import android.content.Intent
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

        /** 供 MainActivity Compose 观察 VPN 运行状态 */
        val isRunningState = mutableStateOf(false)
        var isRunning: Boolean
            get() = isRunningState.value
            private set(value) { isRunningState.value = value }

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
        usbBridge!!.onLinkStateChange = { state ->
            when (state) {
                com.tunnathub.app.usb.LinkState.Connected -> updateNotification("已连接 (USB Bulk)")
                com.tunnathub.app.usb.LinkState.Disconnected -> updateNotification("USB 已断开")
                else -> updateNotification("重连中...")
            }
        }

        scope.launch {
            var lastError: Exception? = null
            for (attempt in 1..3) {
                try {
                    updateNotification("USB 连接中...($attempt/3)")
                    usbBridge!!.start(this)
                    lastError = null
                    break
                } catch (e: Exception) {
                    Log.w(TAG, "USB Bridge 启动失败 (尝试 $attempt/3)", e)
                    lastError = e
                    if (attempt < 3) {
                        updateNotification("重试中...(${attempt}/3)")
                        delay(1500)
                    }
                }
            }
            if (lastError != null) {
                Log.e(TAG, "USB Bridge 3 次重试均失败")
                updateNotification("USB 连接失败: ${lastError.message}")
                stopVpn()
            }
        }

        return START_STICKY
    }

    override fun onDestroy() {
        Log.i(TAG, "VpnService 销毁")
        scope.cancel()
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
