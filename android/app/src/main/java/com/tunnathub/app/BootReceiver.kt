/**
 * BootReceiver.kt — 开机自启 + USB 插拔自动连接
 *
 * BOOT_COMPLETED: 设备启动完成后自动启动 VPN
 * USB_DEVICE_ATTACHED: USB Gadget 插入时自动连接
 */

package com.tunnathub.app

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
                    Log.i(TAG, "TUN_NAT_HUB USB 设备已插入，启动 VPN")
                    startVpnService(context)
                }
            }
        }
    }

    /**
     * 检查 USB 设备是否就绪，然后启动 VPN
     * 开机后 USB 枚举可能需要几秒，这里做简单延迟
     */
    private fun startVpnIfUsbReady(context: Context) {
        // 用独立线程避免阻塞 BroadcastReceiver
        Thread {
            // 等待 USB 子系统就绪（最多 30 秒）
            for (i in 0 until 30) {
                val usbManager = context.getSystemService(Context.USB_SERVICE) as UsbManager
                for ((_, device) in usbManager.deviceList) {
                    if (device.vendorId == UsbBridge.USB_VID &&
                        device.productId == UsbBridge.USB_PID) {
                        Log.i(TAG, "USB 设备已就绪 (尝试 ${i}s)，启动 VPN")
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
