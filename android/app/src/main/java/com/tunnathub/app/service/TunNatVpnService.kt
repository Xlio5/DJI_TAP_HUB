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
import com.tunnathub.app.MainActivity
import com.tunnathub.app.R
import com.tunnathub.app.usb.UsbBridge
import kotlinx.coroutines.*

class TunNatVpnService : VpnService() {

    companion object {
        private const val TAG = "TunNatVpnService"
        private const val NOTIFICATION_ID = 1001
        private const val CHANNEL_ID = "tun_nat_hub_vpn"

        /** 供 MainActivity 查询 VPN 运行状态 */
        @Volatile var isRunning = false
            private set

        // TUN 配置
        private const val TUN_ADDRESS = "10.0.0.2"
        private const val TUN_PREFIX = 24
        private const val TUN_MTU = 1400

        // 路由: 仅捕获局域网流量
        private const val LAN_ROUTE = "192.168.88.0"
        private const val LAN_PREFIX = 24

        // DNS（局域网网关，可选）
        private const val LAN_DNS = "192.168.88.1"
    }

    private var tunFd: ParcelFileDescriptor? = null
    private var usbBridge: UsbBridge? = null
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())

    override fun onCreate() {
        super.onCreate()
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        Log.i(TAG, "VpnService 启动")
        isRunning = true

        // 前台服务
        startForeground(NOTIFICATION_ID, buildNotification("正在启动..."))

        // 建立 TUN 接口
        try {
            tunFd = establishVpn()
            Log.i(TAG, "TUN 接口已建立")
        } catch (e: Exception) {
            Log.e(TAG, "无法建立 TUN", e)
            stopSelf()
            return START_NOT_STICKY
        }

        // 启动 USB Bridge
        usbBridge = UsbBridge(this, tunFd!!)

        scope.launch {
            try {
                updateNotification("连接中...")
                usbBridge!!.start(this)
            } catch (e: Exception) {
                Log.e(TAG, "USB Bridge 异常", e)
                updateNotification("已断开: ${e.message}")
            } finally {
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
        val builder = Builder()
            .setSession(getString(R.string.vpn_service_name))
            .setMtu(TUN_MTU)
            .addAddress(TUN_ADDRESS, TUN_PREFIX)
            .addRoute(LAN_ROUTE, LAN_PREFIX)
            .addDnsServer(LAN_DNS)
            .setBlocking(true)   // 阻塞模式，配合 Dispatchers.IO

        // 排除 VPN 自身流量（如果 App 需要走标准网络栈）
        try {
            builder.addDisallowedApplication(packageName)
        } catch (_: Exception) {
            // 忽略
        }

        return builder.establish()
            ?: throw IllegalStateException("VpnService.Builder.establish() 返回 null")
    }

    /**
     * 停止 VPN
     */
    private fun stopVpn() {
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
