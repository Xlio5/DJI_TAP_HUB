package com.tunnathub.app.usb

import android.accessibilityservice.AccessibilityService
import android.util.Log
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo

/**
 * USB 权限弹窗自动同意 (无障碍服务)。
 *
 * 背景: DJI 遥控器上 `UsbManager.requestPermission` 弹的系统窗
 * (com.android.systemui/.usb.UsbPermissionActivity) **只有"取消/确定", 没有
 * 标准 Android 的"一律允许"复选框**, 系统无从记住; 加上 V3s/DJI RC 反复重枚举
 * USB 使设备路径变化、hasPermission 失效, 于是每次开机都要人工点一次。
 *
 * 为什么不用 Shizuku: Shizuku 服务端 **不支持开机自启**
 * (`ShizukuManager: No support start on boot`), 重启后需 ADB 手动拉起, 覆盖不了开机场景。
 * 无障碍服务由系统托管, 声明 directBootAware 后开机早期(解锁前)就能绑定 —— 而 USB 弹窗
 * 正好出现在开机早期, 所以必须 directBootAware (否则被
 * `AccessibilityManagerService: Ignoring non-encryption-aware service` 忽略)。
 *
 * 识别方式: packageName=systemui + 窗口正文含 "Gadget Serial"(V3s USB gadget 名),
 * 命中后点"确定"(优先 view id, 兜底按文字找可点击祖先)。
 * 不按 className 判断 —— WindowStateChanged 的 className 不保证是 Activity 类名。
 *
 * 启用方式 (一次性, adb 可直接设, 重启保持):
 *   adb shell settings put secure enabled_accessibility_services \
 *       com.tunnathub.app/com.tunnathub.app.usb.UsbPermAccessibilityService
 *   adb shell settings put secure accessibility_enabled 1
 */
class UsbPermAccessibilityService : AccessibilityService() {

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        val e = event ?: return
        if (e.packageName?.toString() != SYSTEMUI_PKG) return

        val root = rootInActiveWindow ?: return

        // 1) USB 设备"打开方式"选择框 (UsbResolverActivity)。
        //    由第三方 App 声明 USB_DEVICE_ATTACHED 引起 (如 QGC), 列表里通常只有那些 App,
        //    选谁都不对(还可能与本项目抢占 V3s 串口) → 直接按返回关掉, 不选任何应用。
        //    用系统资源 id 判定, 语言无关。
        if (root.findAccessibilityNodeInfosByViewId(RESOLVER_LIST_ID).isNotEmpty()) {
            performGlobalAction(GLOBAL_ACTION_BACK)
            Log.i(TAG, "USB 设备选择框已自动关闭 (不选任何应用)")
            return
        }

        // 2) USB 权限弹窗 → 点"确定"
        //    精确识别: 正文含 "Gadget Serial" (V3s USB gadget 名), 避免误点 systemui 其他对话框
        if (root.findAccessibilityNodeInfosByText(USB_GADGET_HINT).isEmpty()) return

        val btn = findOkButton(root) ?: return
        if (btn.performAction(AccessibilityNodeInfo.ACTION_CLICK)) {
            // 用 android.util.Log (Logcat 不依赖存储): direct boot 阶段 App 私有目录尚不可用
            Log.i(TAG, "USB 权限弹窗已自动同意 (无障碍)")
        }
    }

    /**
     * 找"确定"按钮。
     * 优先按 view id (需 config 声明 flagReportViewIds);
     * 兜底按文字"确定"再向上找可点击祖先 (不依赖 flagReportViewIds)。
     */
    private fun findOkButton(root: AccessibilityNodeInfo): AccessibilityNodeInfo? {
        root.findAccessibilityNodeInfosByViewId(BUTTON_OK_ID)?.firstOrNull()?.let { return it }

        for (node in root.findAccessibilityNodeInfosByText(OK_TEXT)) {
            if (node.isClickable) return node
            var parent = node.parent
            var depth = 0
            while (parent != null && depth < MAX_PARENT_DEPTH) {
                if (parent.isClickable) return parent
                parent = parent.parent
                depth++
            }
        }
        return null
    }

    override fun onInterrupt() {}

    companion object {
        private const val TAG = "UsbPermA11y"
        private const val SYSTEMUI_PKG = "com.android.systemui"
        private const val BUTTON_OK_ID = "android:id/button1"
        /** 系统"打开方式/为USB设备选择应用"列表 (语言无关判定) */
        private const val RESOLVER_LIST_ID = "android:id/resolver_list"
        private const val OK_TEXT = "确定"
        /** V3s USB gadget 名 (弹窗正文 "…访问 Gadget Serial v2.4 吗?") */
        private const val USB_GADGET_HINT = "Gadget Serial"
        private const val MAX_PARENT_DEPTH = 4
    }
}
