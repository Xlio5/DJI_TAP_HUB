package com.tunnathub.app.rc

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.isActive
import kotlinx.coroutines.withContext
import rikka.shizuku.Shizuku

/**
 * 通过 Shizuku 以 shell 身份执行 getevent 读高频摇杆。
 *
 * 前置: 设备安装并启动 Shizuku (ADB `sh /sdcard/.../start.sh` 或无线调试方式),
 * 本 App 已获得 Shizuku 权限 (Shizuku.checkSelfPermission()==0)。
 *
 * Shizuku 服务端以 shell UID 起 getevent 真进程, 有 input 组权限可读
 * /dev/input/event*; 替代 AdbGetEventReader 的 adbd 中转 (无 RSA 认证 / 无
 * `adb tcpip` 前置, 链路更稳, 采样率不受 adb 通道限制)。
 *
 * 解析复用 GetEventRcReader 的静态解析器 (EV_ABS 轴 + EV_KEY 按键, 含 KEY_F1..F6)。
 */
class ShizukuGetEventReader(
    private val onSample: (RcInputSample) -> Unit,
    private val eventDevice: String = "/dev/input/event4",
    private val nowMs: () -> Long = { System.currentTimeMillis() }
) : RcReader {

    /** Shizuku 未连接/未授权时直接返回 (上层重试); 否则阻塞读 getevent 流直到进程退出。 */
    override suspend fun run() = withContext(Dispatchers.IO) {
        if (!Shizuku.pingBinder() || Shizuku.checkSelfPermission() != 0) return@withContext
        val process = try {
            Shizuku.newProcess(arrayOf("getevent", "-lt", eventDevice), null, null)
        } catch (_: Exception) {
            return@withContext
        } ?: return@withContext
        val axes = MutableList(6) { 0 }
        val keys = mutableMapOf<String, Int>()
        try {
            process.inputStream.bufferedReader().useLines { lines ->
                val iterator = lines.iterator()
                while (isActive && iterator.hasNext()) {
                    val line = iterator.next()
                    val axis = GetEventRcReader.parseAxisLine(line)
                    if (axis != null) {
                        val idx = GetEventRcReader.DEFAULT_AXIS_MAP[axis.code] ?: continue
                        axes[idx] = GetEventRcReader.normalizeAxis(axis.code, axis.value)
                        onSample(sample(axes, keys))
                        continue
                    }
                    val key = GetEventRcReader.parseKeyLine(line) ?: continue
                    val name = GetEventRcReader.DEFAULT_KEY_MAP[key.code] ?: continue
                    keys[name] = if (key.pressed) 1 else 0
                    onSample(sample(axes, keys))
                }
            }
        } catch (_: Exception) {
            // getevent 进程退出 / Shizuku 断开: 上层捕获后 delay 重试
        } finally {
            try { process.destroy() } catch (_: Exception) {}
        }
    }

    private fun sample(axes: List<Int>, keys: Map<String, Int>): RcInputSample =
        RcInputSample.complete(
            source = "getevent-shizuku",
            axes = axes,
            btn = 0,
            stop = 0,
            focus = 0,
            shot = if ((keys["SHOT"] ?: 0) != 0) 1 else 0,
            rec = if ((keys["REC"] ?: 0) != 0) 1 else 0,
            rth = 0,
            c1 = 0,
            c2 = 0,
            c3 = 0,
            up = 0,
            down = 0,
            left = 0,
            right = 0,
            aircraft = 0,
            back = 0,
            l1 = if ((keys["L1"] ?: 0) != 0) 1 else 0,
            l2 = if ((keys["L2"] ?: 0) != 0) 1 else 0,
            l3 = if ((keys["L3"] ?: 0) != 0) 1 else 0,
            r1 = if ((keys["R1"] ?: 0) != 0) 1 else 0,
            r2 = if ((keys["R2"] ?: 0) != 0) 1 else 0,
            r3 = if ((keys["R3"] ?: 0) != 0) 1 else 0,
            dial = 0,
            mode = "?",
            timestampMs = nowMs()
        )
}
