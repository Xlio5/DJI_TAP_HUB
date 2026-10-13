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

class BootReceiver : BroadcastReceiver() {

    companion object {
        private const val TAG = "BootReceiver"
    }

    override fun onReceive(context: Context, intent: Intent) {
        val pending = goAsync()
        when (intent.action) {
            Intent.ACTION_BOOT_COMPLETED -> {
                Log.i(TAG, "设备启动完成，准备启动 VPN")
                startVpnIfUsbReady(context.applicationContext, pending)
            }
            UsbManager.ACTION_USB_DEVICE_ATTACHED -> {
                val device = intent.getParcelableExtra<android.hardware.usb.UsbDevice>(UsbManager.EXTRA_DEVICE)
                if (device != null && AutoStartPolicy.isTunNatHubUsbDevice(device.vendorId, device.productId)) {
                    // 修复: DJI RC 会周期性重枚举 → ATTACHED 频繁触发。
                    // 服务已启动时由内部重连机制处理；服务未启动时兜底拉起前台 VPN 服务。
                    if (TunNatVpnService.isStartedForUi) {
                        Log.i(TAG, "TUN_NAT_HUB USB 插入 (由 VPN 服务重连机制处理)")
                    } else {
                        Log.i(TAG, "TUN_NAT_HUB USB 插入，启动 VPN 服务")
                        startVpnService(context)
                    }
                }
                pending.finish()
            }
            UsbManager.ACTION_USB_DEVICE_DETACHED -> {
                val device = intent.getParcelableExtra<android.hardware.usb.UsbDevice>(UsbManager.EXTRA_DEVICE)
                if (device != null && AutoStartPolicy.isTunNatHubUsbDevice(device.vendorId, device.productId)) {
                    // 修复: DJI RC 会周期性重枚举 USB → 触发 DETACHED。
                    // 不应停止 VPN 服务, 否则重枚举会把 VPN 杀掉导致断连。
                    // VPN 服务自身 (TunNatVpnService) 已处理 USB 断开重连, 这里只记录日志。
                    Log.i(TAG, "TUN_NAT_HUB USB 拔出 (重枚举? 不停止 VPN, 由服务自行重连)")
                }
                pending.finish()
            }
            AutoStartPolicy.USB_PERMISSION_ACTION -> {
                val granted = intent.getBooleanExtra(UsbManager.EXTRA_PERMISSION_GRANTED, false)
                val device = intent.getParcelableExtra<android.hardware.usb.UsbDevice>(UsbManager.EXTRA_DEVICE)
                if (AutoStartPolicy.shouldStartFromUsbPermission(device?.vendorId, device?.productId, granted)) {
                    Log.i(TAG, "USB 权限回调已授予，启动 VPN 服务")
                    startVpnService(context)
                } else {
                    Log.w(TAG, "USB 权限回调未匹配或未授予，等待下次插入或手动授权")
                }
                pending.finish()
            }
            else -> {
                pending.finish()
            }
        }
    }

    /**
     * 检查 USB 设备是否就绪，请求权限后启动 VPN
     * 开机后 USB 枚举可能需要几秒，这里做简单延迟
     */
    private fun startVpnIfUsbReady(context: Context, pending: PendingResult) {
        Thread {
            try {
                for (i in 0 until AutoStartPolicy.BOOT_USB_SCAN_ATTEMPTS) {
                    val usbManager = context.getSystemService(Context.USB_SERVICE) as UsbManager
                    for ((_, device) in usbManager.deviceList) {
                        if (AutoStartPolicy.isTunNatHubUsbDevice(device.vendorId, device.productId)) {
                            Log.i(TAG, "USB 设备已就绪 (尝试 ${i}s)")
                            // 检查并请求 USB 权限（冷启后可能丢失）
                            if (!usbManager.hasPermission(device)) {
                                Log.w(TAG, "USB 权限未授予，请求中...")
                                val pi = PendingIntent.getBroadcast(
                                    context, 0,
                                    Intent(AutoStartPolicy.USB_PERMISSION_ACTION).setPackage(context.packageName),
                                    PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
                                )
                                usbManager.requestPermission(device, pi)
                                // DJI RC 弹窗无"记住"选项 → Shizuku 自动点"确定"
                                com.tunnathub.app.usb.UsbPermAutoApprover.scheduleApprove()
                                return@Thread
                            }
                            Log.i(TAG, "USB 权限已授予，启动 VPN")
                            startVpnService(context)
                            return@Thread
                        }
                    }
                    Thread.sleep(AutoStartPolicy.BOOT_USB_SCAN_INTERVAL_MS)
                }
                Log.w(TAG, "USB 设备未就绪，等待 USB 插入广播兜底自启")
            } finally {
                pending.finish()
            }
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
