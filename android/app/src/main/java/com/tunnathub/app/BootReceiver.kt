/**
 * BootReceiver.kt — 开机自启 + ECM 网卡检测自动连接
 *
 * BOOT_COMPLETED: 设备启动完成后轮询 ECM 网卡接口，就绪后自动启动 VPN。
 * 不再依赖 USB Host API，改为检测 ECM 网卡接口 (usb0/rndis0)。
 */

package com.tunnathub.app

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Log
import com.tunnathub.app.service.TunNatVpnService
import java.net.NetworkInterface

class BootReceiver : BroadcastReceiver() {

    companion object {
        private const val TAG = "BootReceiver"
    }

    override fun onReceive(context: Context, intent: Intent) {
        when (intent.action) {
            Intent.ACTION_BOOT_COMPLETED -> {
                Log.i(TAG, "设备启动完成，等待 ECM 网卡就绪")
                waitForEcmAndStart(context)
            }
            // ECM 模式下不再需要 USB_DEVICE_ATTACHED/DETACHED
            // 网卡状态变化由系统内核管理
        }
    }

    /**
     * 轮询检测 ECM 网卡接口 (usb0/rndis0) 是否就绪。
     * 开机后 USB Gadget 枚举可能需要数秒。
     */
    private fun waitForEcmAndStart(context: Context) {
        Thread {
            for (i in 0 until 30) {
                val ifaces = NetworkInterface.getNetworkInterfaces()
                while (ifaces.hasMoreElements()) {
                    val name = ifaces.nextElement().name
                    if (name in listOf("usb0", "usb1", "rndis0")) {
                        Log.i(TAG, "ECM 网卡 $name 已就绪 (尝试 ${i}s)，启动 VPN")
                        startVpnService(context)
                        return@Thread
                    }
                }
                Thread.sleep(1000)
            }
            Log.w(TAG, "ECM 网卡 30 秒未就绪，放弃自启")
        }.start()
    }

    private fun startVpnService(context: Context) {
        val intent = Intent(context, TunNatVpnService::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            context.startForegroundService(intent)
        } else {
            context.startService(intent)
        }
    }
}
