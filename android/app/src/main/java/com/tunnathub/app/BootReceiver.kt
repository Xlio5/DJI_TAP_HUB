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
                    Log.i(TAG, "TUN_NAT_HUB USB 已插入，重启 VPN")
                    // 先停止再启动，确保用新的 USB 连接
                    Thread {
                        Thread.sleep(1500)
                        context.stopService(Intent(context, TunNatVpnService::class.java))
                        Thread.sleep(1000)
                        startVpnService(context)
                    }.start()
                }
            }
            UsbManager.ACTION_USB_DEVICE_DETACHED -> {
                val device = intent.getParcelableExtra<android.hardware.usb.UsbDevice>(UsbManager.EXTRA_DEVICE)
                if (device != null &&
                    device.vendorId == UsbBridge.USB_VID &&
                    device.productId == UsbBridge.USB_PID) {
                    Log.i(TAG, "TUN_NAT_HUB USB 已拔出，停止 VPN")
                    context.stopService(Intent(context, TunNatVpnService::class.java))
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
                            val pi = PendingIntent.getBroadcast(
                                context, 0,
                                Intent(UsbManager.ACTION_USB_DEVICE_ATTACHED).setPackage(context.packageName),
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
