package com.tunnathub.app.rc

import com.tunnathub.app.util.AppLog
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.currentCoroutineContext
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import rikka.shizuku.Shizuku

/**
 * 通过 Shizuku 以 shell 身份执行 getevent，读高频摇杆与按键。
 *
 * **完全按 V3s 侧实现对齐**（ubuntu/src/dji_rc.cpp `adb_multiplex_thread` +
 * `adb_process_getevent_chunk`，解析规则见 adb_getevent_rc.cpp）：
 *
 *   1. V3s 开**两个** getevent 流（不是把所有设备读成一条）：
 *        - event4 (摇杆): `getevent -lp <dev>; exec getevent -lt <dev>`  ← 先快照当前值再持续
 *        - event3 (按键): `exec getevent -lt <dev>`
 *   2. 分派规则（V3s 的 `joystick_stream` 标志）：
 *        - 摇杆流: 轴 + 按键都处理
 *        - 按键流: **只**处理按键
 *   3. 轴映射 / 数值缩放 / 按键映射与 `adb_getevent_rc.cpp` 完全一致
 *      （ABS_RX/RY/Y/X/RZ/Z → ch0..5；Z/RZ 走 (v-127)*660/128，其余 v*660/32768）
 *
 * 说明：App 用 Shizuku 拿 shell 身份，V3s 自带 adb 客户端直连 adbd —— **传输层不同，
 * 处理逻辑刻意保持一致**，这样同一条摇杆/按键在 App 显示与 V3s 输出上能对得上。
 */
class ShizukuGetEventReader(
    private val onSample: (RcInputSample) -> Unit,
    private val nowMs: () -> Long = { System.currentTimeMillis() }
) : RcReader {

    /** 两流共享的状态（对齐 V3s 的 g_adb_getevent_rc，单实例 + 锁保护） */
    private val stateLock = Any()
    private val axes = MutableList(6) { 0 }
    private val keys = mutableMapOf<String, Int>()

    override suspend fun run() = withContext(Dispatchers.IO) {
        if (!shizukuReady()) return@withContext

        val joystickProc = newProcess(SHELL_EVENT4) ?: return@withContext
        val keyProc = newProcess(SHELL_EVENT3)
        if (keyProc == null) {
            runCatching { joystickProc.destroy() }
            return@withContext
        }
        AppLog.i(TAG, "getevent 双流已启动 (event4 摇杆+按键 / event3 按键)")
        try {
            coroutineScope {
                launch { readStream(joystickProc, isAxisStream = true) }
                launch { readStream(keyProc, isAxisStream = false) }
            }
            AppLog.i(TAG, "getevent 流结束 (进程退出)")
        } catch (e: Exception) {
            AppLog.w(TAG, "getevent 读取异常: $e")
        } finally {
            runCatching { joystickProc.destroy() }
            runCatching { keyProc.destroy() }
        }
    }

    /**
     * 逐行消费一个流。
     * [isAxisStream] = true 时该流的轴事件才生效（对齐 V3s 的 joystick_stream：
     * 轴只认摇杆流，按键两条流都收）。
     */
    private suspend fun readStream(proc: Process, isAxisStream: Boolean) =
        withContext(Dispatchers.IO) {
            try {
                proc.inputStream.bufferedReader().useLines { lines ->
                    for (line in lines) {
                        if (!currentCoroutineContext().isActive) break
                        handleLine(line, isAxisStream)
                    }
                }
            } catch (_: Exception) {
                // 流断开（Shizuku 掉线/getevent 退出）：上层 RcFusionRuntime 会重试重建
            }
        }

    private fun handleLine(line: String, isAxisStream: Boolean) {
        val axis = GetEventRcReader.parseAxisLine(line)
        if (axis != null && isAxisStream) {
            val idx = GetEventRcReader.DEFAULT_AXIS_MAP[axis.code] ?: return
            synchronized(stateLock) {
                axes[idx] = GetEventRcReader.normalizeAxis(axis.code, axis.value)
            }
            onSample(sample())
            return
        }
        val key = GetEventRcReader.parseKeyLine(line) ?: return
        val name = GetEventRcReader.DEFAULT_KEY_MAP[key.code] ?: return
        synchronized(stateLock) { keys[name] = if (key.pressed) 1 else 0 }
        onSample(sample())
    }

    private fun sample(): RcInputSample = synchronized(stateLock) {
        RcInputSample.complete(
            source = SOURCE,
            axes = axes.toList(),
            btn = 0,
            stop = 0,
            focus = 0,
            shot = keys.bit("SHOT"),
            rec = keys.bit("REC"),
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
            l1 = keys.bit("L1"),
            l2 = keys.bit("L2"),
            l3 = keys.bit("L3"),
            r1 = keys.bit("R1"),
            r2 = keys.bit("R2"),
            r3 = keys.bit("R3"),
            dial = 0,
            mode = "?",
            timestampMs = nowMs()
        )
    }

    private fun shizukuReady(): Boolean = try {
        Shizuku.pingBinder() && Shizuku.checkSelfPermission() == 0
    } catch (_: Exception) {
        false
    }

    private fun newProcess(shellCmd: String): Process? = try {
        Shizuku.newProcess(arrayOf("sh", "-c", shellCmd), null, null)
    } catch (e: Exception) {
        AppLog.w(TAG, "getevent newProcess 失败: $e")
        null
    }

    companion object {
        private const val TAG = "ShizukuReader"
        private const val SOURCE = "getevent-shizuku"

        /** 摇杆流 —— 对齐 V3s `build_getevent_shell(dev, /*snapshot_axes=*/true)` */
        private const val SHELL_EVENT4 =
            "getevent -lp /dev/input/event4; exec getevent -lt /dev/input/event4"

        /** 按键流 —— 对齐 V3s 的 `aux_device = "/dev/input/event3"` */
        private const val SHELL_EVENT3 = "exec getevent -lt /dev/input/event3"
    }
}

private fun Map<String, Int>.bit(name: String): Int =
    if ((this[name] ?: 0) != 0) 1 else 0
