/**
 * LuaParamController.kt — ELRS 参数配置控制器
 *
 * 协调 CrsfBridge (UDP) + LuaEngine (Lua 脚本) + UI 状态。
 * 流程:
 *   V3s 转发 CRSF 参数帧 → CrsfBridge.onFrame → LuaEngine.telemetryFrame
 *   → lcd.drawText 回调 → UI rows
 *   用户操作 → event() → crossfireTelemetryPush → CrsfBridge.sendFrame
 */
package com.tunnathub.app.crsf

import android.content.Context
import android.util.Log

class LuaParamController(private val context: Context) {
    private val TAG = "LuaParamController"

    private var rows = mutableListOf<ParamRow>()
    var onRowsChanged: (() -> Unit)? = null

    private val lineMap = sortedMapOf<Int, MutableList<Pair<Int, String>>>()  // y → (x,text)
    private var selectedLine = 0

    init {
        // Lua lcd.drawText → 行
        LuaEngine.onLine = { line ->
            lineMap.getOrPut(line.y) { mutableListOf() }.add(line.x to line.text)
            rebuildRows()
        }
        // Lua crossfireTelemetryPush → 发 CRSF 帧
        LuaEngine.onCrsfSend = { type, frame ->
            if (frame.isNotEmpty()) CrsfBridge.sendFrame(frame)
        }
        // V3s 转发 CRSF 帧 → Lua
        CrsfBridge.onFrame = { frame ->
            LuaEngine.telemetryFrame(frame)
        }
    }

    private fun rebuildRows() {
        rows = lineMap.toSortedMap().map { (y, items) ->
            val text = items.sortedBy { it.first }.joinToString("") { it.second }
            ParamRow(text, selected = false)
        }.toMutableList()
        // 标记选中行
        if (rows.isNotEmpty()) {
            val idx = selectedLine.coerceIn(0, rows.size - 1)
            rows[idx] = rows[idx].copy(selected = true)
        }
        onRowsChanged?.invoke()
    }

    fun start(host: String) {
        if (!LuaEngine.isReady()) LuaEngine.init()
        CrsfBridge.start(host)
        loadElrsLua()
        // 触发设备发现
        CrsfBridge.sendFrame(buildDevicePing())
    }

    fun stop() {
        CrsfBridge.stop()
    }

    /** 加载 assets 里的 elrsV3.lua */
    private fun loadElrsLua() {
        try {
            val script = context.assets.open("elrsV3.lua").bufferedReader().use { it.readText() }
            LuaEngine.loadScript(script)
        } catch (e: Exception) {
            Log.e(TAG, "load elrsV3.lua fail: $e")
        }
    }

    fun up() { selectedLine = (selectedLine - 1).coerceAtLeast(0); LuaEngine.event("UP"); rebuildRows() }
    fun down() { selectedLine = (selectedLine + 1).coerceAtMost((rows.size - 1).coerceAtLeast(0)); LuaEngine.event("DOWN"); rebuildRows() }
    fun enter() { LuaEngine.event("ENTER") }
    fun exit() { LuaEngine.event("EXIT") }
    fun reload() {
        lineMap.clear()
        selectedLine = 0
        CrsfBridge.sendFrame(buildDevicePing())
        LuaEngine.runFrame()
        rebuildRows()
    }

    fun getRows(): List<ParamRow> = rows

    /** Device_Ping 扩展帧: [0xC8][4][0x28][dest=0xEE][orig=0xEA][crc] */
    private fun buildDevicePing(): ByteArray {
        val frame = ByteArray(7)
        frame[0] = 0xC8.toByte()
        frame[1] = 0x04
        frame[2] = 0x28.toByte()
        frame[3] = 0xEE.toByte()
        frame[4] = 0xEA.toByte()
        frame[5] = crc8(frame, 5)
        return frame
    }

    private val crcTable = crcTable()
    private fun crc8(data: ByteArray, len: Int): Byte {
        var c = 0
        for (i in 0 until len) c = crcTable[(c xor (data[i].toInt() and 0xFF)) and 0xFF]
        return c.toByte()
    }
    private fun crcTable(): IntArray {
        val t = IntArray(256)
        for (i in 0 until 256) {
            var c = i
            for (j in 0 until 8) c = if ((c and 0x80) != 0) ((c shl 1) xor 0xD5) and 0xFF else (c shl 1) and 0xFF
            t[i] = c
        }
        return t
    }
}
