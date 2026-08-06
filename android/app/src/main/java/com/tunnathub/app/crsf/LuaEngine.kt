/**
 * LuaEngine.kt — ELRS Lua 脚本引擎 (LuaJ) + EdgeTX API 绑定
 *
 * 绑定 elrsV3.lua 依赖的核心 API:
 *   crossfireTelemetryPush(type, {bytes})  — 发 CRSF 帧到网口 (V3s → UART0)
 *   lcd.drawText(x, y, str, attr)          — 绘制参数行 (映射到 Compose UI)
 *   lcd.getLastPos() / lcd.sizeText()
 *   bit32 / string / math — 标准库
 *   EdgeTX 脚本约定: loadScript/run/event + 常量 BOLD/CHAR_UP/CHAR_DOWN
 */
package com.tunnathub.app.crsf

import android.util.Log
import org.luaj.vm2.Globals
import org.luaj.vm2.LuaInteger
import org.luaj.vm2.LuaString
import org.luaj.vm2.LuaTable
import org.luaj.vm2.LuaValue
import org.luaj.vm2.Varargs
import org.luaj.vm2.lib.OneArgFunction
import org.luaj.vm2.lib.TwoArgFunction
import org.luaj.vm2.lib.VarArgFunction
import org.luaj.vm2.lib.jse.JsePlatform

/** 参数界面的一行 (Lua lcd.drawText 结果) */
data class LuaLine(val x: Int, val y: Int, val text: String, val attr: Int)

object LuaEngine {
    private const val TAG = "LuaEngine"

    private var globals: Globals? = null
    private val crsf = CrsfBridge

    /** Lua → App 回调 */
    @Volatile
    var onLine: ((LuaLine) -> Unit)? = null      // lcd.drawText 绘制行
    @Volatile
    var onCrsfSend: ((Int, ByteArray) -> Unit)? = null  // crossfireTelemetryPush

    /** Lua 环境是否就绪 */
    fun isReady(): Boolean = globals != null

    /** 初始化 Lua 环境 + 绑定 EdgeTX API */
    fun init() {
        try {
            val g = JsePlatform.standardGlobals()
            bindEdgeTxApi(g)
            globals = g
            Log.i(TAG, "Lua engine ready")
        } catch (e: Throwable) {
            Log.e(TAG, "Lua init fail: $e")
        }
    }

    /** 加载并运行 Lua 脚本 (elrsV3.lua), 执行 loadScript + run */
    fun loadScript(script: String): Boolean {
        val g = globals ?: return false
        return try {
            g.load(script, "elrsV3.lua").call()
            // EdgeTX 约定: loadScript() 返回 true 表示成功
            val loadFn = g.get("loadScript")
            if (loadFn.isfunction()) loadFn.call()
            true
        } catch (e: Throwable) {
            Log.e(TAG, "loadScript fail: $e")
            false
        }
    }

    /** 每帧调用 run() (脚本主循环) */
    fun runFrame() {
        val g = globals ?: return
        try {
            val fn = g.get("run")
            if (fn.isfunction()) fn.call()
        } catch (e: Throwable) {
            Log.w(TAG, "run fail: $e")
        }
    }

    /** 用户输入 → event() 回调 (如旋转/按键) */
    fun event(evt: String) {
        val g = globals ?: return
        try {
            val fn = g.get("event")
            if (fn.isfunction()) fn.call(LuaValue.valueOf(evt))
        } catch (e: Throwable) {
            Log.w(TAG, "event fail: $e")
        }
    }

    /** 注入 CRSF 帧数据到 Lua (Device_Info/Settings_Entry 回调) */
    fun telemetryFrame(frame: ByteArray) {
        val g = globals ?: return
        try {
            val fn = g.get("setFieldValue")
            if (fn.isfunction()) {
                // ELRS 脚本用 setFieldValue/filedChunk 接收 Settings_Entry 数据
                fn.call(LuaValue.valueOf(frame.size), LuaValue.valueOf(frame), LuaValue.TRUE)
            }
            runFrame()
        } catch (e: Throwable) {
            Log.w(TAG, "telemetryFrame fail: $e")
        }
    }

    // ── EdgeTX API 绑定 ──
    private fun bindEdgeTxApi(g: Globals) {
        // crossfireTelemetryPush(type, {bytes}) — 发 CRSF 帧
        g.set("crossfireTelemetryPush", object : TwoArgFunction() {
            override fun call(type: LuaValue, data: LuaValue): LuaValue {
                val t = type.toint()
                val bytes = ByteArray(data.length())
                for (i in 0 until data.length()) {
                    bytes[i] = data.get(i + 1).toint().toByte()
                }
                // 构造 CRSF 帧: [0xC8][len][type][payload][crc] — payload 前补 dest/orig
                val crsfFrame = buildCrsfFrame(t, bytes)
                onCrsfSend?.invoke(t, crsfFrame)
                return LuaValue.TRUE
            }
        })

        // lcd 表
        val lcd = LuaTable()
        lcd.set("drawText", object : VarArgFunction() {
            override fun invoke(args: Varargs): Varargs {
                val x = args.arg1().toint()
                val y = args.arg(2).toint()
                val str = args.arg(3).tojstring()
                val attr = if (args.narg() >= 4) args.arg(4).toint() else 0
                onLine?.invoke(LuaLine(x, y, str, attr))
                return LuaValue.NONE
            }
        })
        lcd.set("getLastPos", object : OneArgFunction() {
            override fun call(arg: LuaValue): LuaValue = LuaInteger.valueOf(0)
        })
        lcd.set("sizeText", object : OneArgFunction() {
            override fun call(arg: LuaValue): LuaValue = LuaInteger.valueOf(arg.tojstring().length * 10)
        })
        g.set("lcd", lcd)

        // 常量
        g.set("BOLD", LuaValue.valueOf(2))
        g.set("CHAR_UP", LuaValue.valueOf("↑"))
        g.set("CHAR_DOWN", LuaValue.valueOf("↓"))
        g.set("__opentx", LuaValue.TRUE)   // 兼容脚本版本检查
        g.set("__edgeos", LuaValue.FALSE)
    }

    /** 构造 CRSF 扩展帧 (0x28+): [addr][len][type][dest][orig][payload][crc]
     * crossfireTelemetryPush 的 payload 已含 dest/orig/数据 */
    private fun buildCrsfFrame(type: Int, payload: ByteArray): ByteArray {
        // ELRS 脚本 payload = [dest][orig][data...]
        if (payload.size < 2) return ByteArray(0)
        val data = payload.copyOfRange(2, payload.size)
        val plen = data.size
        val len = plen + 4
        val frame = ByteArray(len + 2)
        frame[0] = 0xC8.toByte()          // addr (FC/TX)
        frame[1] = len.toByte()
        frame[2] = type.toByte()
        frame[3] = payload[0]             // dest
        frame[4] = payload[1]             // orig
        if (plen > 0) data.copyInto(frame, 5)
        frame[len + 1] = crc8(frame, len)
        return frame
    }

    /** CRSF CRC-8 poly 0xD5 */
    private val crcTable = crcTable()
    private fun crc8(data: ByteArray, len: Int): Byte {
        var c = 0
        for (i in 0 until len) {
            c = crcTable[(c xor (data[i].toInt() and 0xFF)) and 0xFF]
        }
        return c.toByte()
    }
    private fun crcTable(): IntArray {
        val t = IntArray(256)
        for (i in 0 until 256) {
            var c = i
            for (j in 0 until 8) {
                c = if ((c and 0x80) != 0) ((c shl 1) xor 0xD5) and 0xFF else (c shl 1) and 0xFF
            }
            t[i] = c
        }
        return t
    }
}
