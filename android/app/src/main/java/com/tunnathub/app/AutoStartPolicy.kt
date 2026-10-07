package com.tunnathub.app

import android.content.Intent
import android.hardware.usb.UsbManager

/** USB/开机自启动策略。保持纯判断可单元测试，Android 细节留在 Receiver/Service。 */
object AutoStartPolicy {
    const val USB_PERMISSION_ACTION = "com.tunnathub.app.USB_PERM"
    const val USB_VID = 0x0BDA
    const val USB_PID = 0x8812
    const val BOOT_USB_SCAN_ATTEMPTS = 5
    const val BOOT_USB_SCAN_INTERVAL_MS = 1_000L
    const val BROADCAST_ASYNC_BUDGET_MS = 9_000L

    fun isTunNatHubUsbDevice(vendorId: Int, productId: Int): Boolean =
        vendorId == USB_VID && productId == USB_PID

    fun shouldTryAutoStart(action: String?): Boolean =
        action == Intent.ACTION_BOOT_COMPLETED ||
            action == UsbManager.ACTION_USB_DEVICE_ATTACHED ||
            action == USB_PERMISSION_ACTION

    fun shouldRequestUsbPermission(vendorId: Int, productId: Int, hasPermission: Boolean): Boolean =
        isTunNatHubUsbDevice(vendorId, productId) && !hasPermission

    fun shouldStartFromUsbPermission(vendorId: Int?, productId: Int?, granted: Boolean): Boolean =
        granted &&
            vendorId != null &&
            productId != null &&
            isTunNatHubUsbDevice(vendorId, productId)

    fun bootScanBudgetMs(): Long =
        BOOT_USB_SCAN_ATTEMPTS * BOOT_USB_SCAN_INTERVAL_MS
}

fun isTunNatHubUsbDeviceForTest(vendorId: Int, productId: Int): Boolean =
    AutoStartPolicy.isTunNatHubUsbDevice(vendorId, productId)

fun shouldTryAutoStartForTest(action: String?): Boolean =
    AutoStartPolicy.shouldTryAutoStart(action)

fun shouldRequestUsbPermissionForTest(vendorId: Int, productId: Int, hasPermission: Boolean): Boolean =
    AutoStartPolicy.shouldRequestUsbPermission(vendorId, productId, hasPermission)

fun shouldStartFromUsbPermissionForTest(vendorId: Int?, productId: Int?, granted: Boolean): Boolean =
    AutoStartPolicy.shouldStartFromUsbPermission(vendorId, productId, granted)
