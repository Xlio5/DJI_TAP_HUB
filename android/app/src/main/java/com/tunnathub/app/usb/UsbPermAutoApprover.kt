package com.tunnathub.app.usb

import com.tunnathub.app.util.AppLog
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import rikka.shizuku.Shizuku

/**
 * USB 权限弹窗自动同意 (DJI RC 无人值守场景)。
 *
 * 背景: DJI 遥控器上 `UsbManager.requestPermission` 会弹系统窗
 * (com.android.systemui/.usb.UsbPermissionActivity), 且该弹窗**只有"取消/确定"、
 * 没有标准 Android 的"一律允许"复选框** → 系统无从记住。加上 V3s/DJI RC 会反复
 * 重枚举 USB, 设备路径 (/dev/bus/usb/00X/00Y) 变化后 hasPermission 变 false,
 * 于是每次开机/重枚举都要人工点一次"确定"。
 *
 * 方案: 复用 App 已有的 Shizuku (shell 身份) 模拟点击 —— 请求权限后延迟片刻,
 * 检测到弹窗就用 `uiautomator dump` 解析"确定"按钮坐标, 再 `input tap` 点掉。
 * 全程在 App 内完成, 无需用户操作、无需 root、无需无障碍服务。
 *
 * 前提: Shizuku 已安装且本 App 已授权 (与 getevent 高频读取同一套授权)。
 * Shizuku 不可用时静默跳过 —— 退化为手动点"确定", 不影响主流程。
 */
object UsbPermAutoApprover {
    private const val TAG = "UsbPermAuto"

    /** 弹窗出现的等待时间 (requestPermission 返回后 systemui 才起 Activity) */
    private const val DEFAULT_DELAY_MS = 900L

    /** 最多重试几次 (弹窗出现有延迟，保险多试两轮) */
    private const val MAX_ATTEMPTS = 3

    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private var pending: Job? = null

    /**
     * 请求 USB 权限后调用: 延迟后在后台自动点掉弹窗。
     * 重复调用只保留最后一次 (避免连点)。
     */
    @JvmStatic
    fun scheduleApprove(delayMs: Long = DEFAULT_DELAY_MS) {
        pending?.cancel()
        pending = scope.launch {
            repeat(MAX_ATTEMPTS) { attempt ->
                delay(if (attempt == 0) delayMs else 1200L)
                if (!shizukuReady()) return@launch
                if (approveOnce()) {
                    AppLog.i(TAG, "USB 权限弹窗已自动同意")
                    return@launch
                }
            }
            AppLog.w(TAG, "未检测到 USB 权限弹窗 (可能已自动授予/无弹窗)")
        }
    }

    /** 检测并点击一次。返回 true = 找到弹窗并点了"确定"。 */
    private fun approveOnce(): Boolean {
        // 1) 弹窗是否在前台 (dumpsys 输出很大, 只找关键字)
        val acts = exec("dumpsys", "activity", "activities")
        if (!acts.contains("UsbPermissionActivity")) return false

        // 2) dump 当前界面, 解析"确定"按钮中心坐标
        exec("uiautomator", "dump", DUMP_PATH)
        val xml = exec("cat", DUMP_PATH)
        val m = BUTTON1_RE.find(xml) ?: return false
        val x = (m.groupValues[1].toInt() + m.groupValues[3].toInt()) / 2
        val y = (m.groupValues[2].toInt() + m.groupValues[4].toInt()) / 2

        // 3) 点击
        exec("input", "tap", x.toString(), y.toString())
        AppLog.i(TAG, "点击弹窗\"确定\" @ ($x, $y)")
        return true
    }

    private fun shizukuReady(): Boolean = try {
        Shizuku.pingBinder() && Shizuku.checkSelfPermission() == 0
    } catch (_: Exception) {
        false
    }

    /** 以 shell 身份执行命令并读回 stdout (Shizuku)。失败返回空串。 */
    private fun exec(vararg cmd: String): String {
        return try {
            val p = Shizuku.newProcess(cmd, null, null) ?: return ""
            val out = p.inputStream.bufferedReader().use { it.readText() }
            p.waitFor()
            out
        } catch (e: Exception) {
            AppLog.w(TAG, "shizuku exec ${cmd.joinToString(" ")} 失败: ${e.message}")
            ""
        }
    }

    private const val DUMP_PATH = "/sdcard/usbperm_auto.xml"

    /** 匹配 uiautomator dump 里 android:id/button1 (确定) 的 bounds */
    private val BUTTON1_RE =
        Regex("""resource-id="android:id/button1"[^>]*bounds="\[(\d+),(\d+)]\[(\d+),(\d+)]"""")
}
