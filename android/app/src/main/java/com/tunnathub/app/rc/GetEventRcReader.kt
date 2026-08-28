package com.tunnathub.app.rc

import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.isActive
import kotlinx.coroutines.withContext

/** 读取 DJI RC 的 getevent 输出并转换为 RC 轴和按键。 */
class GetEventRcReader(
    private val eventDevice: String? = null,
    private val axisMap: Map<String, Int> = DEFAULT_AXIS_MAP,
    private val keyMap: Map<String, String> = DEFAULT_KEY_MAP,
    private val onSample: (RcInputSample) -> Unit,
    private val nowMs: () -> Long = { System.currentTimeMillis() }
) : RcReader {
    data class AxisEvent(val code: String, val value: Int)
    data class KeyEvent(val code: String, val pressed: Boolean)

    override suspend fun run() = withContext(Dispatchers.IO) {
        val axes = MutableList(6) { 0 }
        val keys = mutableMapOf<String, Int>()
        val command = mutableListOf("getevent", "-lt")
        eventDevice?.let(command::add)
        val process = ProcessBuilder(command)
            .redirectErrorStream(true)
            .start()
        try {
            process.inputStream.bufferedReader().useLines { lines ->
                val iterator = lines.iterator()
                while (isActive && iterator.hasNext()) {
                    val line = iterator.next()
                    val axis = parseAxisLine(line)
                    if (axis != null) {
                        val idx = axisMap[axis.code] ?: continue
                        axes[idx] = normalizeAxis(axis.code, axis.value)
                        onSample(sampleFromState(axes, keys, nowMs()))
                        continue
                    }

                    val key = parseKeyLine(line) ?: continue
                    val name = keyMap[key.code] ?: continue
                    keys[name] = if (key.pressed) 1 else 0
                    onSample(sampleFromState(axes, keys, nowMs()))
                }
            }
        } finally {
            process.destroy()
        }
    }

    private fun sampleFromState(
        axes: List<Int>,
        keys: Map<String, Int>,
        timestampMs: Long
    ): RcInputSample =
        RcInputSample.complete(
            source = "getevent",
            axes = axes,
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
            timestampMs = timestampMs
        )

    companion object {
        val DEFAULT_AXIS_MAP: Map<String, Int> = mapOf(
            "ABS_RX" to 0,
            "ABS_RY" to 1,
            "ABS_Y" to 2,
            "ABS_X" to 3,
            "ABS_RZ" to 4,
            "ABS_Z" to 5
        )

        val DEFAULT_KEY_MAP: Map<String, String> = mapOf(
            "BTN_TL" to "REC",
            "BTN_TR" to "SHOT",
            "KEY_F1" to "L1",
            "KEY_F2" to "L2",
            "KEY_F3" to "L3",
            "KEY_F4" to "R1",
            "KEY_F5" to "R2",
            "KEY_F6" to "R3"
        )

        @JvmStatic
        fun sampleForTest(
            axes: List<Int>,
            keys: Map<String, Int>,
            timestampMs: Long
        ): RcInputSample =
            GetEventRcReader(onSample = {}).sampleFromState(axes, keys, timestampMs)

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
            "ABS_Z", "ABS_RZ" -> ((raw.coerceIn(0, 255) - 127) * 660 / 128).coerceIn(-660, 660)
            else -> (raw.coerceIn(-32768, 32767) * 660 / 32768).coerceIn(-660, 660)
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

private fun Map<String, Int>.bit(name: String): Int = if ((this[name] ?: 0) != 0) 1 else 0
