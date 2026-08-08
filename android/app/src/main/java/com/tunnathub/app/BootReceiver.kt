/**
 * BootReceiver.kt — 开机自启 + USB 插拔自动连接
 *
 * BOOT_COMPLETED: 设备启动完成后自动启动 VPN
 * USB_DEVICE_ATTACHED: USB Gadget 插入时自动连接
 */

package com.tunnathub.app

import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.hardware.usb.UsbManager
import android.os.Build
import android.util.Log
import com.tunnathub.app.service.TunNatVpnService
import com.tunnathub.app.usb.UsbBridge

class BootReceiver : BroadcastReceiver() {

    companion object {
        private const val TAG = "BootReceiver"
    }

    override fun onReceive(context: Context, intent: Intent) {
        when (intent.action) {
            Intent.ACTION_BOOT_COMPLETED -> {
                Log.i(TAG, "设备启动完成，准备启动 VPN")
                startVpnIfUsbReady(context)
            }
            UsbManager.ACTION_USB_DEVICE_ATTACHED -> {
                val device = intent.getParcelableExtra<android.hardware.usb.UsbDevice>(UsbManager.EXTRA_DEVICE)
                if (device != null &&
                    device.vendorId == UsbBridge.USB_VID &&
                    device.productId == UsbBridge.USB_PID) {
                    // 修复: DJI RC 会周期性重枚举 → ATTACHED 频繁触发。
                    // 不应停止再重启 VPN (会打断运行), 也不应重复 startVpnService
                    // (会触发 onStartCommand 的 isStarted 残留强制重启)。
                    // 由 TunNatVpnService 自身的重连机制处理即可。
                    Log.i(TAG, "TUN_NAT_HUB USB 插入 (由 VPN 服务重连机制处理)")
                }
            }
            UsbManager.ACTION_USB_DEVICE_DETACHED -> {
                val device = intent.getParcelableExtra<android.hardware.usb.UsbDevice>(UsbManager.EXTRA_DEVICE)
                if (device != null &&
                    device.vendorId == UsbBridge.USB_VID &&
                    device.productId == UsbBridge.USB_PID) {
                    // 修复: DJI RC 会周期性重枚举 USB → 触发 DETACHED。
                    // 不应停止 VPN 服务, 否则重枚举会把 VPN 杀掉导致断连。
                    // VPN 服务自身 (TunNatVpnService) 已处理 USB 断开重连, 这里只记录日志。
                    Log.i(TAG, "TUN_NAT_HUB USB 拔出 (重枚举? 不停止 VPN, 由服务自行重连)")
                }
            }
        }
    }

    /**
     * 检查 USB 设备是否就绪，请求权限后启动 VPN
     * 开机后 USB 枚举可能需要几秒，这里做简单延迟
     */
    private fun startVpnIfUsbReady(context: Context) {
        Thread {
            for (i in 0 until 30) {
                val usbManager = context.getSystemService(Context.USB_SERVICE) as UsbManager
                for ((_, device) in usbManager.deviceList) {
                    if (device.vendorId == UsbBridge.USB_VID &&
                        device.productId == UsbBridge.USB_PID) {
                        Log.i(TAG, "USB 设备已就绪 (尝试 ${i}s)")
                        // 检查并请求 USB 权限（冷启后可能丢失）
                        if (!usbManager.hasPermission(device)) {
                            Log.w(TAG, "USB 权限未授予，请求中...")
                            // H-06: 用应用私有 action 接收权限回调 (不能复用系统广播 ACTION_USB_DEVICE_ATTACHED,
                            // 该 action 的接收分支只查 EXTRA_DEVICE, 权限回调无此 extra → 结果被静默丢弃)
                            val pi = PendingIntent.getBroadcast(
                                context, 0,
                                Intent("com.tunnathub.app.USB_PERM").setPackage(context.packageName),
                                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
                            )
                            usbManager.requestPermission(device, pi)
                            // 权限是异步的，等 1 秒后重试
                            Thread.sleep(1000)
                            continue
                        }
                        Log.i(TAG, "USB 权限已授予，启动 VPN")
                        startVpnService(context)
                        return@Thread
                    }
                }
                Thread.sleep(1000)
            }
            Log.w(TAG, "USB 设备 30 秒未就绪，放弃自启")
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
