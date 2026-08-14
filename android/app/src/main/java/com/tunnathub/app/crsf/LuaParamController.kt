/**
 * LuaParamController.kt — ELRS 参数配置控制器
 *
 * 协调 CrsfBridge (UDP) + LuaEngine (Lua 脚本) + UI 状态。
 * 流程:
 *   V3s 转发 CRSF 参数帧 → CrsfBridge.onFrame → LuaEngine.telemetryFrame 入队
 *   → Lua run() 消费 (crossfireTelemetryPop) → lcd.drawText 回调 → UI rows
 *   用户操作 → run(EVT_*) → Lua → crossfireTelemetryPush → CrsfBridge.sendFrame
 */
package com.tunnathub.app.crsf

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.util.Log
import kotlin.concurrent.thread

class LuaParamController(private val context: Context) {
    private val TAG = "LuaParamController"

    private var rows = mutableListOf<ParamRow>()
    var onRowsChanged: (() -> Unit)? = null
    /** 当前设备名 (标题栏) */
    var onTitleChanged: ((String) -> Unit)? = null

    private val lineMap = sortedMapOf<Int, MutableList<Pair<Int, String>>>()  // y → (x,text)
    private var hasRowData = false   // Lua 是否已画出参数行 (区分"加载中"与"无参数")
    private var title = "ELRS"       // 标题栏设备名 (y=4 的 drawText)
    private val uiHandler = Handler(Looper.getMainLooper())
    private var luaTick: Runnable? = null
    private var running = false

    init {
        // Lua lcd.drawText → 行 (选中行用 INVERS 属性标记)
        LuaEngine.onLine = { line ->
            Log.d(TAG, "onLine y=${line.y} '${line.text}'")
            if (line.text.isNotEmpty()) {
                lineMap.getOrPut(line.y) { mutableListOf() }.add(line.x to line.text)
                if (line.attr and LuaEngine.INVERS != 0) {
                    // 选中行标记: 记下这个 y 是选中
                    hasRowData = true
                }
            }
            rebuildRows()
        }
        // Lua lcd.clear → 清空行
        LuaEngine.onClear = {
            Log.d(TAG, "onClear 清空行")
            lineMap.clear()
            hasRowData = false
            rebuildRows()
        }
        // Lua crossfireTelemetryPush → 发 CRSF 帧 (mock 模式不建网络, 忽略)
        LuaEngine.onCrsfSend = { type, frame ->
            if (frame.isNotEmpty() && !LuaEngine.useMock) CrsfBridge.sendFrame(frame)
        }
        // V3s 转发 CRSF 帧 → Lua 消息队列
        CrsfBridge.onFrame = { frame ->
            LuaEngine.telemetryFrame(frame)
            LuaEngine.runFrame(0)
        }
    }

    private fun rebuildRows() {
        // 标题栏 (y < 31): 取最左的 deviceName 作标题
        lineMap.filterKeys { it < 31 }.forEach { (y, items) ->
            items.minByOrNull { it.first }?.let { title = it.second }
        }
        // 参数行 (y >= 31): 按 y 分组, 同 y 内按 x 拼接
        rows = lineMap.filterKeys { it >= 31 }.toSortedMap().map { (y, items) ->
            val sorted = items.sortedBy { it.first }
            val text = StringBuilder()
            var prevX = -1
            for ((x, s) in sorted) {
                if (prevX >= 0 && x - prevX > 6 && text.isNotEmpty()) text.append("  ")
                text.append(s)
                prevX = x + s.length * 6  // 估算下一段起始
            }
            ParamRow(text.toString(), selected = false)
        }.toMutableList()
        Log.d(TAG, "rebuildRows ${rows.size} 行 title='$title'")
        onRowsChanged?.invoke()
        onTitleChanged?.invoke(title)
    }

    fun start(host: String) {
        if (!LuaEngine.isReady()) LuaEngine.init(context)
        if (!LuaEngine.useMock) {
            // 真机模式: 建网络连接 + 设备发现
            CrsfBridge.start(host)
            loadElrsLua()
            CrsfBridge.sendFrame(buildDevicePing())
        } else {
            // mock 模式: 不建网络, elrs.lua setMock() 直接加载假数据
            Log.i(TAG, "mock 模式: 加载假数据 (不连 V3s)")
            loadElrsLua()
        }
        // 驱动首帧渲染
        LuaEngine.runFrame(0)
        // 周期驱动 Lua (每 100ms), 让 refreshNext 持续发 Settings_Read/消费帧
        running = true
        val tick = object : Runnable {
            override fun run() {
                if (!running) return
                LuaEngine.runFrame(0)
                uiHandler.postDelayed(this, 100)
            }
        }
        luaTick = tick
        uiHandler.post(tick)
    }

    fun stop() {
        running = false
        luaTick?.let { uiHandler.removeCallbacks(it) }
        luaTick = null
        if (!LuaEngine.useMock) CrsfBridge.stop()
    }

    /** 加载 assets 里的 elrs.lua */
    private fun loadElrsLua() {
        try {
            val script = context.assets.open("elrs.lua").bufferedReader().use { it.readText() }
            LuaEngine.loadScript(script)
        } catch (e: Exception) {
            Log.e(TAG, "load elrs.lua fail: $e")
        }
    }

    fun up()    = LuaEngine.event(EVT_VIRTUAL_PREV)
    fun down()  = LuaEngine.event(EVT_VIRTUAL_NEXT)
    fun enter() = LuaEngine.event(EVT_VIRTUAL_ENTER)
    fun exit()  = LuaEngine.event(EVT_VIRTUAL_EXIT)
    fun reload() {
        lineMap.clear()
        hasRowData = false
        CrsfBridge.sendFrame(buildDevicePing())
        LuaEngine.runFrame(0)
    }

    fun getRows(): List<ParamRow> = rows

    /** Device_Ping 扩展帧: [0xEE][4][0x28][dest=0x00广播][orig=0xEA][crc]
     *  参考 elrs_lua_python: addr=0xEE, dest=0x00, CRC 只对 [type][dest][orig] */
    private fun buildDevicePing(): ByteArray {
        val frame = ByteArray(6)
        frame[0] = 0xEE.toByte()
        frame[1] = 0x04
        frame[2] = 0x28.toByte()
        frame[3] = 0x00
        frame[4] = 0xEA.toByte()
        frame[5] = crc8(frame, 2, 5)
        return frame
    }

    private val crcTable = crcTable()
    private fun crc8(data: ByteArray, from: Int, to: Int): Byte {
        var c = 0
        for (i in from until to) c = crcTable[(c xor (data[i].toInt() and 0xFF)) and 0xFF]
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
