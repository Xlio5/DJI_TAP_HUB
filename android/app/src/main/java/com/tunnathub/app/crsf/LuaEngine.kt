/**
 * LuaEngine.kt — ELRS Lua 脚本引擎 (LuaJ) + EdgeTX API 绑定
 *
 * 对接 elrsV3.lua (EdgeTX 返回-table 约定):
 *   loadScript() 接收脚本返回值 { init=, run= }
 *   runFrame(event) 调用 module.run(event)
 *   消息流: App 收 CRSF 帧 → telemetryFrame 解析入队 → Lua crossfireTelemetryPop 取
 *   Lua lcd.drawText → onLine 回调 → Compose UI
 *   用户操作 → runFrame(EVT_*) → Lua → crossfireTelemetryPush → 网口
 */
package com.tunnathub.app.crsf

import android.util.Log
import org.luaj.vm2.Globals
import org.luaj.vm2.LuaInteger
import org.luaj.vm2.LuaTable
import org.luaj.vm2.LuaValue
import org.luaj.vm2.Varargs
import org.luaj.vm2.lib.OneArgFunction
import org.luaj.vm2.lib.ThreeArgFunction
import org.luaj.vm2.lib.TwoArgFunction
import org.luaj.vm2.lib.VarArgFunction
import org.luaj.vm2.lib.ZeroArgFunction
import org.luaj.vm2.lib.jse.JsePlatform
import java.util.ArrayDeque

/** 参数界面的一行 (Lua lcd.drawText 结果) */
data class LuaLine(val x: Int, val y: Int, val text: String, val attr: Int)

/** EdgeTX 事件常量 */
const val EVT_VIRTUAL_ENTER = 0x0008
const val EVT_VIRTUAL_EXIT  = 0x0009
const val EVT_VIRTUAL_PREV  = 0x0010
const val EVT_VIRTUAL_NEXT  = 0x0011
const val EVT_TOUCH_TAP     = 0x0301

object LuaEngine {
    private const val TAG = "LuaEngine"

    // ---- 常量 (EdgeTX 兼容) ----
    const val BOLD   = 2
    const val BLINK  = 16
    const val INVERS = 8
    const val CENTER = 128
    const val RIGHT  = 64
    const val MIDSIZE = 32
    const val CUSTOM_COLOR = 0xF0
    const val BLACK = 0
    const val WHITE = 15
    const val SOLID = 0
    const val GREY_DEFAULT = 0x55
    const val COLOR_THEME_DISABLED = 0x3F
    const val LCD_W = 220
    const val LCD_H = 176

    private var globals: Globals? = null
    private var module: LuaTable? = null        // elrs.lua 返回的 {init=, run=}
    private var appContext: android.content.Context? = null
    private val msgQueue = ArrayDeque<Pair<Int, ByteArray>>()  // (command, payload[dest,orig,data...])

    /** 模拟器假数据模式: getVersion 返回 -simu 结尾 → elrs.lua setMock() 加载 elrsmock.lua
     * 默认自动判断: 模拟器 → true (离线调试), 真机 → false (走真实 V3s crsf-bridge) */
    @Volatile
    var useMock = false

    /** 是否 Android 模拟器 (x86/emulator 特征) */
    fun isEmulator(): Boolean {
        val fp = android.os.Build.FINGERPRINT
        val model = android.os.Build.MODEL
        val mfr = android.os.Build.MANUFACTURER
        val brand = android.os.Build.BRAND
        val dev = android.os.Build.DEVICE
        return (fp.startsWith("generic") || fp.startsWith("unknown") ||
            model.contains("google_sdk") || model.contains("Emulator") ||
            model.contains("Android SDK built for x86") ||
            mfr.contains("Genymotion") ||
            (brand.startsWith("generic") && dev.startsWith("generic")) ||
            "google_sdk" == android.os.Build.PRODUCT)
    }

    /** Lua → App 回调 */
    @Volatile
    var onLine: ((LuaLine) -> Unit)? = null       // lcd.drawText 绘制行
    @Volatile
    var onCrsfSend: ((Int, ByteArray) -> Unit)? = null  // crossfireTelemetryPush
    @Volatile
    var onClear: (() -> Unit)? = null             // lcd.clear

    private val crsf = CrsfBridge

    /** Lua 环境是否就绪 */
    fun isReady(): Boolean = globals != null

    /** 初始化 Lua 环境 + 绑定 EdgeTX API */
    fun init(context: android.content.Context) {
        appContext = context.applicationContext
        useMock = isEmulator()
        Log.i(TAG, "useMock=$useMock (emulator=${isEmulator()})")
        try {
            val g = JsePlatform.standardGlobals()
            bindEdgeTxApi(g)
            globals = g
            Log.i(TAG, "Lua engine ready")
        } catch (e: Throwable) {
            Log.e(TAG, "Lua init fail: $e")
        }
    }

    /**
     * 加载并运行 Lua 脚本 (elrs.lua)。
     * 脚本顶层执行后返回 { init=, run= } table (EdgeTX 约定), 存为模块引用并调用 init()。
     */
    fun loadScript(script: String): Boolean {
        val g = globals ?: return false
        return try {
            val ret = g.load(script, "elrs.lua").call()
            if (ret.istable()) {
                module = ret.checktable()
                val initFn = module!!.get("init")
                if (initFn.isfunction()) {
                    initFn.call()
                    Log.i(TAG, "elrs.lua loaded + init() called")
                }
                true
            } else {
                Log.w(TAG, "脚本未返回 table, 按全局约定兜底")
                val loadFn = g.get("loadScript")
                if (loadFn.isfunction()) loadFn.call()
                true
            }
        } catch (e: Throwable) {
            Log.e(TAG, "loadScript fail: $e")
            false
        }
    }

    /** 每帧调用 module.run(event), 驱动 Lua 渲染 + 事件处理 */
    fun runFrame(event: Int) {
        val m = module ?: return
        try {
            val fn = m.get("run")
            if (fn.isfunction()) fn.call(LuaValue.valueOf(event))
        } catch (e: Throwable) {
            Log.w(TAG, "run fail: $e")
        }
    }

    /** 用户输入 → run(EVT_*) */
    fun event(evt: Int) = runFrame(evt)

    /** 注入 CRSF 帧到消息队列 (App 收 UART0 上行 → Lua crossfireTelemetryPop) */
    fun telemetryFrame(frame: ByteArray) {
        // wire: [addr][len][type][dest][orig][data...][crc]
        if (frame.size < 6) return
        val type = frame[2].toInt() and 0xFF
        // data = [dest][orig][data...] (跳过 addr/len/type, 排除末尾 crc)
        val payload = frame.copyOfRange(3, frame.size - 1)
        Log.d(TAG, "telemetryFrame type=0x${type.toString(16)} len=${payload.size} head=${payload.take(8).joinToString(" "){ "%02x".format(it) }}")
        msgQueue.addLast(type to payload)
    }

    // ── EdgeTX API 绑定 ──
    private fun bindEdgeTxApi(g: Globals) {
        // crossfireTelemetryPush(type, {bytes}) — 发 CRSF 帧
        g.set("crossfireTelemetryPush", object : TwoArgFunction() {
            override fun call(type: LuaValue, data: LuaValue): LuaValue {
                val t = type.toint()
                val n = data.length()
                val payload = ByteArray(n)
                for (i in 0 until n) payload[i] = data.get(i + 1).toint().toByte()
                Log.d(TAG, "crossfireTelemetryPush type=0x${t.toString(16)} payload=${payload.take(6).joinToString(" "){ "%02x".format(it) }}")
                val frame = buildCrsfFrame(t, payload)
                onCrsfSend?.invoke(t, frame)
                return LuaValue.TRUE
            }
        })

        // crossfireTelemetryPop() — 从消息队列取 (command, payload)
        g.set("crossfireTelemetryPop", object : VarArgFunction() {
            override fun invoke(args: Varargs): Varargs {
                return synchronized(msgQueue) {
                    val e = msgQueue.pollFirst()
                    if (e != null) {
                        val cmd = LuaValue.valueOf(e.first)
                        val tbl = LuaTable()
                        for (i in e.second.indices) tbl.set(i + 1, LuaValue.valueOf(e.second[i].toInt() and 0xFF))
                        Log.d(TAG, "crossfireTelemetryPop type=0x${e.first.toString(16)} payload=${e.second.take(6).joinToString(" "){ "%02x".format(it) }}")
                        LuaValue.varargsOf(arrayOf(cmd, tbl))
                    } else {
                        LuaValue.varargsOf(arrayOf(LuaValue.NIL, LuaValue.NIL))
                    }
                }
            }
        })

        // getTime() — EdgeTX 10ms tick (脚本所有超时值均按 tick 计)
        g.set("getTime", object : ZeroArgFunction() {
            override fun call(): LuaValue = LuaInteger.valueOf((android.os.SystemClock.uptimeMillis() / 10).toInt())
        })

        // getVersion() — (nil, version, major, minor, rev, osname)
        // useMock 时版本带 "-simu" 后缀 → elrs.lua setMock() 加载假数据
        g.set("getVersion", object : VarArgFunction() {
            override fun invoke(args: Varargs): Varargs {
                val ver = if (useMock) "2.4.0-simu" else "2.4.0"
                return LuaValue.varargsOf(
                    arrayOf(
                        LuaValue.NIL, LuaValue.valueOf(ver), LuaValue.valueOf(2),
                        LuaValue.valueOf(4), LuaValue.valueOf(0), LuaValue.valueOf("EdgeTX")
                    )
                )
            }
        })

        // loadScript(path) — 从 assets 加载子脚本 (elrs.lua setMock 调 mockup/elrsmock.lua)
        g.set("loadScript", object : VarArgFunction() {
            override fun invoke(args: Varargs): Varargs {
                val path = args.arg1().tojstring()
                val ctx = appContext
                if (ctx == null) return LuaValue.varargsOf(arrayOf(LuaValue.NIL))
                return try {
                    val stream = ctx.assets.open(path)
                    val script = stream.bufferedReader().use { it.readText() }
                    g.load(script, path).invoke()
                } catch (e: Exception) {
                    Log.e(TAG, "loadScript $path fail: $e")
                    LuaValue.varargsOf(arrayOf(LuaValue.NIL))
                }
            }
        })

        // model 表
        val model = LuaTable()
        model.set("getModule", object : OneArgFunction() {
            override fun call(arg: LuaValue): LuaValue {
                val m = LuaTable()
                m.set("Type", LuaValue.valueOf(5))   // CRSF
                return m
            }
        })
        model.set("getInfo", object : ZeroArgFunction() {
            override fun call(): LuaValue = LuaTable()
        })
        g.set("model", model)

        // popupConfirmation(text, button, event) → 返回 "OK" 允许确认
        g.set("popupConfirmation", object : VarArgFunction() {
            override fun invoke(args: Varargs): Varargs = LuaValue.valueOf("OK")
        })

        // lcd 表
        val lcd = LuaTable()
        lcd.set("clear", object : ZeroArgFunction() {
            override fun call(): LuaValue {
                Log.d(TAG, "lcd.clear")
                onClear?.invoke()
                return LuaValue.NONE
            }
        })
        lcd.set("RGB", object : ThreeArgFunction() {
            override fun call(a: LuaValue, b: LuaValue, c: LuaValue): LuaValue =
                LuaInteger.valueOf((a.toint() shl 16) or (b.toint() shl 8) or c.toint())
        })
        lcd.set("setColor", object : TwoArgFunction() {
            override fun call(a: LuaValue, b: LuaValue): LuaValue = LuaValue.NONE
        })
        lcd.set("drawText", object : VarArgFunction() {
            override fun invoke(args: Varargs): Varargs {
                val x = args.arg1().toint()
                val y = args.arg(2).toint()
                val str = args.arg(3).tojstring()
                val attr = if (args.narg() >= 4) args.arg(4).toint() else 0
                Log.d(TAG, "drawText x=$x y=$y str='$str' attr=$attr")
                onLine?.invoke(LuaLine(x, y, str, attr))
                return LuaValue.NONE
            }
        })
        lcd.set("drawRectangle", object : VarArgFunction() {
            override fun invoke(args: Varargs): Varargs = LuaValue.NONE
        })
        lcd.set("drawFilledRectangle", object : VarArgFunction() {
            override fun invoke(args: Varargs): Varargs = LuaValue.NONE
        })
        lcd.set("drawLine", object : VarArgFunction() {
            override fun invoke(args: Varargs): Varargs = LuaValue.NONE
        })
        lcd.set("drawGauge", object : VarArgFunction() {
            override fun invoke(args: Varargs): Varargs = LuaValue.NONE
        })
        lcd.set("getLastPos", object : OneArgFunction() {
            override fun call(arg: LuaValue): LuaValue = LuaInteger.valueOf(0)
        })
        lcd.set("sizeText", object : VarArgFunction() {
            override fun invoke(args: Varargs): Varargs {
                val text = args.arg1().tojstring()
                val w = text.length * 10
                return LuaValue.varargsOf(arrayOf(LuaInteger.valueOf(w), LuaInteger.valueOf(21)))
            }
        })
        g.set("lcd", lcd)

        // print → logcat (Lua 调试输出)
        g.set("print", object : VarArgFunction() {
            override fun invoke(args: Varargs): Varargs {
                val sb = StringBuilder()
                for (i in 1..args.narg()) sb.append(args.arg(i).tojstring()).append(" ")
                Log.i(TAG, "Lua: $sb")
                return LuaValue.NONE
            }
        })

        // 常量
        g.set("BOLD", LuaValue.valueOf(BOLD))
        g.set("BLINK", LuaValue.valueOf(BLINK))
        g.set("INVERS", LuaValue.valueOf(INVERS))
        g.set("CENTER", LuaValue.valueOf(CENTER))
        g.set("RIGHT", LuaValue.valueOf(RIGHT))
        g.set("MIDSIZE", LuaValue.valueOf(MIDSIZE))
        g.set("CUSTOM_COLOR", LuaValue.valueOf(CUSTOM_COLOR))
        g.set("BLACK", LuaValue.valueOf(BLACK))
        g.set("WHITE", LuaValue.valueOf(WHITE))
        g.set("SOLID", LuaValue.valueOf(SOLID))
        g.set("GREY_DEFAULT", LuaValue.valueOf(GREY_DEFAULT))
        g.set("COLOR_THEME_DISABLED", LuaValue.valueOf(COLOR_THEME_DISABLED))
        g.set("LCD_W", LuaValue.valueOf(LCD_W))
        g.set("LCD_H", LuaValue.valueOf(LCD_H))
        g.set("CHAR_UP", LuaValue.valueOf("↑"))
        g.set("CHAR_DOWN", LuaValue.valueOf("↓"))
        g.set("__opentx", LuaValue.TRUE)   // 兼容脚本版本检查
        g.set("__edgeos", LuaValue.FALSE)
        g.set("EVT_VIRTUAL_ENTER", LuaValue.valueOf(EVT_VIRTUAL_ENTER))
        g.set("EVT_VIRTUAL_EXIT", LuaValue.valueOf(EVT_VIRTUAL_EXIT))
        g.set("EVT_VIRTUAL_PREV", LuaValue.valueOf(EVT_VIRTUAL_PREV))
        g.set("EVT_VIRTUAL_NEXT", LuaValue.valueOf(EVT_VIRTUAL_NEXT))
        g.set("EVT_TOUCH_TAP", LuaValue.valueOf(EVT_TOUCH_TAP))
    }

    /** 构造 CRSF 扩展帧: [addr][len][type][dest][orig][payload][crc]
     *  参考 elrs_lua_python/crsf.py build_extended_frame:
     *  addr=0xEE(CRSF TX 模块), CRC 只对 [type][dest][orig][payload] 计算 (不含 addr/len) */
    private fun buildCrsfFrame(type: Int, payload: ByteArray): ByteArray {
        if (payload.size < 2) return ByteArray(0)
        val data = payload.copyOfRange(2, payload.size)
        val plen = data.size
        val len = plen + 4
        val frame = ByteArray(len + 2)
        frame[0] = 0xEE.toByte()
        frame[1] = len.toByte()
        frame[2] = type.toByte()
        frame[3] = payload[0]
        frame[4] = payload[1]
        if (plen > 0) data.copyInto(frame, 5)
        frame[len + 1] = crc8(frame, 2, len)
        return frame
    }

    private val crcTable = crcTable()
    private fun crc8(data: ByteArray, from: Int, to: Int): Byte {
        var c = 0
        for (i in from until to) {
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
