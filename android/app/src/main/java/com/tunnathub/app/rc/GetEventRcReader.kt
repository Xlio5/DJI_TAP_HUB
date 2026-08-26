package com.tunnathub.app.rc

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.isActive
import kotlinx.coroutines.withContext

/** 读取 DJI embedded joystick 的 getevent 输出并转换为 RC 轴。 */
class GetEventRcReader(
    private val eventDevice: String = "/dev/input/event4",
    private val axisMap: Map<String, Int> = DEFAULT_AXIS_MAP,
    private val onSample: (RcInputSample) -> Unit,
    private val nowMs: () -> Long = { System.currentTimeMillis() }
) {
    data class AxisEvent(val code: String, val value: Int)
    data class KeyEvent(val code: String, val pressed: Boolean)

    suspend fun run() = withContext(Dispatchers.IO) {
        val axes = MutableList(6) { 0 }
        val process = ProcessBuilder("getevent", "-lt", eventDevice)
            .redirectErrorStream(true)
            .start()
        process.inputStream.bufferedReader().useLines { lines ->
            val iterator = lines.iterator()
            while (isActive && iterator.hasNext()) {
                val line = iterator.next()
                val axis = parseAxisLine(line)
                if (axis != null) {
                    val idx = axisMap[axis.code] ?: continue
                    axes[idx] = normalizeAxis(axis.code, axis.value)
                    onSample(RcInputSample.axes("getevent", axes.toList(), nowMs()))
                }
            }
        }
    }

    companion object {
        val DEFAULT_AXIS_MAP: Map<String, Int> = mapOf(
            "ABS_X" to 0,
            "ABS_Y" to 1,
            "ABS_RX" to 2,
            "ABS_RY" to 3,
            "ABS_Z" to 4,
            "ABS_RZ" to 5
        )

        @JvmStatic
        fun parseAxisLine(line: String): AxisEvent? {
            if (!line.contains(" EV_ABS ")) return null
            val parts = line.trim().split(Regex("\\s+"))
            val typeIndex = parts.indexOf("EV_ABS")
            if (typeIndex < 0 || typeIndex + 2 >= parts.size) return null
            val value = parseEventValue(parts[typeIndex + 2]) ?: return null
            return AxisEvent(parts[typeIndex + 1], value)
        }

        @JvmStatic
        fun parseKeyLine(line: String): KeyEvent? {
            if (!line.contains(" EV_KEY ")) return null
            val parts = line.trim().split(Regex("\\s+"))
            val typeIndex = parts.indexOf("EV_KEY")
            if (typeIndex < 0 || typeIndex + 2 >= parts.size) return null
            val value = parseEventValue(parts[typeIndex + 2]) ?: return null
            return KeyEvent(parts[typeIndex + 1], value != 0)
        }

        @JvmStatic
        fun normalizeAxis(code: String, raw: Int): Int = when (code) {
            "ABS_Z", "ABS_RZ" -> ((raw.coerceIn(0, 255) - 127) * 1024 / 128).coerceIn(-1024, 1024)
            else -> (raw.coerceIn(-32768, 32767) * 1024 / 32768).coerceIn(-1024, 1024)
        }

        private fun parseEventValue(text: String): Int? {
            if (text == "DOWN") return 1
            if (text == "UP") return 0
            val negative = text.startsWith("-")
            val body = if (negative) text.substring(1) else text
            val parsed = if (body.any { it in 'a'..'f' || it in 'A'..'F' }) {
                body.toLongOrNull(16)
            } else {
                body.toLongOrNull(16) ?: body.toLongOrNull()
            } ?: return null
            val signed = if (negative) -parsed else parsed
            return signed.toInt()
        }
    }
}
