package com.tunnathub.app.rc

import android.content.Context
import android.util.Base64
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.InputStream
import java.io.OutputStream
import java.net.Socket
import java.nio.ByteBuffer
import java.nio.ByteOrder
import java.security.KeyFactory
import java.security.PrivateKey
import java.security.Signature
import java.security.spec.PKCS8EncodedKeySpec
import java.util.zip.CRC32

/**
 * 通过 adb 协议连本机 adbd, 以 shell 权限执行 getevent 读高频摇杆。
 *
 * 前置: 手机已 `adb tcpip 5555` 开启 adbd 网络监听, 且本机 adbd 信任
 * assets/adbkey 对应公钥 (与电脑 adb 共用 key, 电脑 adb 连过即信任)。
 *
 * adbd 进程有 input 组 (uid shell groups 含 1004), 执行 getevent 能读
 * /dev/input/event4; 普通 App 无该权限, 走 adbd 中转绕过 DAC 限制。
 * adbd 开启 RSA 认证 (ro.adb.secure=1), 需用私钥签名 AUTH token 才能执行命令。
 */
class AdbGetEventReader(
    private val context: Context,
    private val onSample: (RcInputSample) -> Unit,
    private val host: String = "127.0.0.1",
    private val port: Int = 5555,
    private val nowMs: () -> Long = { System.currentTimeMillis() }
) : RcReader {
    private val privateKey: PrivateKey? = loadAdbKey()

    private fun loadAdbKey(): PrivateKey? {
        return try {
            val pem = context.assets.open("adbkey").bufferedReader().readText()
            val b64 = pem
                .replace("-----BEGIN PRIVATE KEY-----", "")
                .replace("-----END PRIVATE KEY-----", "")
                .replace(Regex("\\s"), "")
            val der = Base64.decode(b64, Base64.DEFAULT)
            KeyFactory.getInstance("RSA").generatePrivate(PKCS8EncodedKeySpec(der))
        } catch (e: Exception) {
            null
        }
    }
    private val axes = IntArray(6)
    private val keys = mutableMapOf<String, Int>()
    private val axisMap = mapOf(
        "ABS_RX" to 0, "ABS_RY" to 1, "ABS_Y" to 2, "ABS_X" to 3, "ABS_RZ" to 4, "ABS_Z" to 5
    )
    private val keyMap = mapOf("BTN_TL" to "REC", "BTN_TR" to "SHOT")

    /** 连接 adbd 并持续读 getevent 流, 直到 socket 断开 (上层异常重试)。 */
    override suspend fun run() = withContext(Dispatchers.IO) {
        var sock: Socket? = null
        try {
            sock = Socket(host, port)
            sock.tcpNoDelay = true
            val input = sock.getInputStream()
            val output = sock.getOutputStream()

            // 1. CNXN 握手 (version + maxdata + banner)
            writePacket(output, "CNXN", VERSION, MAXDATA, "host::tunnathub_adb".toByteArray())

            // 2. 处理 adbd RSA 认证 (ro.adb.secure=1): AUTH TOKEN → 私钥签名 → AUTH SIGNATURE
            var pkt = readPacket(input) ?: return@withContext
            if (pkt.cmd == "AUTH" && pkt.arg0 == 1) {
                val key = privateKey ?: return@withContext
                val sig = try {
                    Signature.getInstance("SHA1withRSA").run {
                        initSign(key)
                        update(pkt.data)
                        sign()
                    }
                } catch (e: Exception) { return@withContext }
                writePacket(output, "AUTH", 2, 0, sig)
                pkt = readPacket(input) ?: return@withContext   // adbd 验证通过回 CNXN
            }
            if (pkt.cmd != "CNXN") return@withContext

            // 3. OPEN exec 服务 (raw 传输, 等同电脑 `adb exec-out`)
            writePacket(output, "OPEN", 1, 0,
                "exec:getevent -lt /dev/input/event4".toByteArray())
            // adbd 回 OKAY, 之后 WRTE 数据流

            // 3. 读 WRTE 流, 按行解析 getevent 事件
            val lineBuf = StringBuilder()
            while (true) {
                val pkt = readPacket(input) ?: break
                when (pkt.cmd) {
                    "WRTE" -> {
                        lineBuf.append(String(pkt.data, Charsets.UTF_8))
                        var idx: Int
                        while (lineBuf.indexOf("\n").also { idx = it } >= 0) {
                            val line = lineBuf.substring(0, idx).trimEnd('\r')
                            lineBuf.delete(0, idx + 1)
                            if (line.isNotEmpty()) parseLine(line)
                        }
                    }
                    "CLSE" -> break
                    else -> { /* OKAY / 其他忽略 */ }
                }
            }
        } catch (_: Exception) {
            // adbd 未开 / 连接断开: 上层 RcFusionRuntime 捕获后 delay 重试
        } finally {
            sock?.close()
        }
    }

    /** getevent 行示例: [ 123.456] /dev/input/event4: EV_ABS ABS_RX 00008000 */
    private fun parseLine(line: String) {
        val m = ABS_RE.find(line)
        if (m != null) {
            val idx = axisMap[m.groupValues[1]] ?: return
            var v = m.groupValues[2].toIntOrNull(16) ?: return
            if (v >= 0x8000) v -= 0x10000
            axes[idx] = v
            onSample(sample())
            return
        }
        val k = KEY_RE.find(line) ?: return
        val name = keyMap[k.groupValues[1]] ?: return
        keys[name] = when (k.groupValues[2]) {
            "DOWN" -> 1
            "UP" -> 0
            else -> if (k.groupValues[2] != "0") 1 else 0
        }
        onSample(sample())
    }

    private fun sample(): RcInputSample =
        RcInputSample.complete(
            source = "getevent-adb",
            axes = axes.toList(),
            btn = 0, stop = 0, focus = 0,
            shot = keys["SHOT"] ?: 0, rec = keys["REC"] ?: 0,
            rth = 0, c1 = 0, c2 = 0, c3 = 0,
            up = 0, down = 0, left = 0, right = 0, aircraft = 0, back = 0,
            l1 = 0, l2 = 0, l3 = 0, r1 = 0, r2 = 0, r3 = 0,
            dial = 0, mode = "?", timestampMs = nowMs()
        )

    // ── adb wire 协议 ─────────────────────────────────────────────
    // 包格式 (24B header): [cmd:4B][arg0:4B][arg1:4B][len:4B][data_check:4B CRC32][magic:4B cmd^0xFFFFFFFF][data...]

    private fun writePacket(out: OutputStream, cmd: String, arg0: Int, arg1: Int, data: ByteArray) {
        val c = ByteArray(4)
        cmd.toByteArray(Charsets.US_ASCII).copyInto(c, 0, 0, minOf(4, cmd.length))
        val cmdInt = ByteBuffer.wrap(c).order(ByteOrder.LITTLE_ENDIAN).int
        val crc = CRC32().apply { update(data) }.value.toInt()
        val magic = cmdInt xor -1   // 0xFFFFFFFF
        val header = ByteBuffer.allocate(24).order(ByteOrder.LITTLE_ENDIAN)
        header.put(c)
        header.putInt(arg0)
        header.putInt(arg1)
        header.putInt(data.size)
        header.putInt(crc)
        header.putInt(magic)
        out.write(header.array())
        if (data.isNotEmpty()) out.write(data)
        out.flush()
    }

    private fun readPacket(input: InputStream): AdbPacket? {
        val header = ByteArray(24)
        var off = 0
        while (off < 24) {
            val n = input.read(header, off, 24 - off)
            if (n < 0) return null
            off += n
        }
        val bb = ByteBuffer.wrap(header).order(ByteOrder.LITTLE_ENDIAN)
        val cmd = String(header, 0, 4, Charsets.US_ASCII)
        val len = bb.getInt(12)
        val data = ByteArray(len)
        var dOff = 0
        while (dOff < len) {
            val n = input.read(data, dOff, len - dOff)
            if (n < 0) return null
            dOff += n
        }
        return AdbPacket(cmd, bb.getInt(4), bb.getInt(8), data)
    }

    private data class AdbPacket(val cmd: String, val arg0: Int, val arg1: Int, val data: ByteArray)

    companion object {
        private const val VERSION = 0x01000001
        private const val MAXDATA = 65536
        private val ABS_RE = Regex("""EV_ABS\s+(\w+)\s+([0-9a-fA-F]+)""")
        private val KEY_RE = Regex("""EV_KEY\s+(\w+)\s+([0-9a-fA-F]+|DOWN|UP)""")
    }
}
