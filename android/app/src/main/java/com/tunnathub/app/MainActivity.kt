/**
 * MainActivity.kt — TUN_NAT_HUB v1.2.0
 * 新 UI：顶部固定状态栏 + 左侧导航栏(视频/配置) + 右侧内容区
 * V3s: USB 同线供电, 设备需 10s 启动 → 自动轮询发现 + 自动连接
 */

package com.tunnathub.app

import android.app.PendingIntent
import android.content.*
import android.hardware.usb.UsbDevice
import android.hardware.usb.UsbManager
import android.net.VpnService
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.view.SurfaceView
import android.widget.FrameLayout
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Radio
import androidx.compose.material.icons.filled.Send
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.SportsEsports
import androidx.compose.material3.*
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import com.tunnathub.app.BuildConfig
import com.tunnathub.app.service.TunNatVpnService
import com.tunnathub.app.usb.UsbBridge
import com.tunnathub.app.util.AppLog
import com.tunnathub.app.video.Media3RtspProbePlayer
import com.tunnathub.app.video.RtspPlaybackEngine
import com.tunnathub.app.video.RtspUdpProbe
import com.tunnathub.app.video.UdpRtspPlayer
import kotlinx.coroutines.*
import org.easydarwin.video.BenchmarkStats
import org.easydarwin.video.LowLatencyRtspPlayer
import org.easydarwin.video.RtspPlayerSession
import rikka.shizuku.Shizuku

/** Activity 与 Compose 共享的播放器引用，用于 onDestroy 时释放 */
private val playerHolder = java.util.concurrent.atomic.AtomicReference<RtspPlayerSession?>(null)

// ── 输入源数值配置 (与 V3s rc_map rc_cfg_names 对齐) ──
private data class SrcCfgRow(val key: String, val label: String, val rev: Boolean = false, val def: Int = 1500)

private val SRC_CFG_GROUPS: List<Pair<String, List<SrcCfgRow>>> = buildList {
    // 摇杆/模拟
    add("摇杆 / 模拟" to buildList {
        for (i in 1..6) {
            add(SrcCfgRow("st${i}_min", "STICK$i 最小", def = 1000))
            add(SrcCfgRow("st${i}_max", "STICK$i 最大", def = 2000))
            add(SrcCfgRow("st${i}_mid", "STICK$i 中位", def = 1500))
            add(SrcCfgRow("st${i}_rev", "STICK$i 反向", rev = true, def = 0))
        }
        add(SrcCfgRow("dial_min", "DIAL 最小", def = 1000))
        add(SrcCfgRow("dial_max", "DIAL 最大", def = 2000))
        add(SrcCfgRow("dial_rev", "DIAL 反向", rev = true, def = 0))
    })
    // MODE 三档
    add("三档 MODE" to listOf(
        SrcCfgRow("mode_s", "S 档", def = 1000),
        SrcCfgRow("mode_n", "N 档", def = 1500),
        SrcCfgRow("mode_f", "F 档", def = 2000),
    ))
    // 2 档开关
    add("开关 (14个)" to buildList {
        val sw = listOf(
            "rec" to "REC", "rth" to "RTH", "stop" to "STOP", "focus" to "FOCUS",
            "c1" to "C1", "c2" to "C2", "c3" to "C3", "aircraft" to "AIRCRAFT",
            "back" to "BACK", "btn" to "BTN", "up" to "UP", "down" to "DOWN",
            "left" to "LEFT", "right" to "RIGHT",
        )
        for ((k, l) in sw) {
            add(SrcCfgRow("${k}_off", "$l 关", def = 1000))
            add(SrcCfgRow("${k}_on", "$l 开", def = if (k == "focus") 1500 else 2000))
            add(SrcCfgRow("${k}_lp", "$l 长按", rev = true, def = 0))
        }
    })
    // SHOT 快门
    add("SHOT 快门" to listOf(
        SrcCfgRow("shot_lo", "松", def = 1000),
        SrcCfgRow("shot_mid", "半按", def = 1500),
        SrcCfgRow("shot_hi", "全按", def = 2000),
    ))
    // C12 四档
    add("C12 四档" to listOf(
        SrcCfgRow("c12_0", "无", def = 1000),
        SrcCfgRow("c12_1", "C1", def = 1333),
        SrcCfgRow("c12_2", "C2", def = 1667),
        SrcCfgRow("c12_3", "C1+C2", def = 2000),
    ))
    // DIR 六档
    add("DIR 六档" to listOf(
        SrcCfgRow("dir_0", "无", def = 1000),
        SrcCfgRow("dir_1", "UP", def = 1200),
        SrcCfgRow("dir_2", "DN", def = 1400),
        SrcCfgRow("dir_3", "L", def = 1600),
        SrcCfgRow("dir_4", "R", def = 1800),
        SrcCfgRow("dir_5", "BTN", def = 2000),
    ))
    // L1-R3 六档 (互斥自锁)
    add("L1-R3 六档" to listOf(
        SrcCfgRow("lr_0", "L1", def = 1000),
        SrcCfgRow("lr_1", "L2", def = 1200),
        SrcCfgRow("lr_2", "L3", def = 1400),
        SrcCfgRow("lr_3", "R1", def = 1600),
        SrcCfgRow("lr_4", "R2", def = 1800),
        SrcCfgRow("lr_5", "R3", def = 2000),
    ))
}

private const val CHANNEL_COUNT = 16
private val DEFAULT_CHANNEL_SOURCES = listOf(
    "ch1", "ch2", "ch3", "ch4", "ch5", "ch6",
    "mode", "rec", "rth", "focus", "aircraft", "dial", "stop", "c12", "c3", "dir"
)
private val DEFAULT_CHANNEL_MAP = channelMapToString(DEFAULT_CHANNEL_SOURCES)

private data class SourceKeys(
    val minKey: String = "",
    val maxKey: String = "",
    val midKey: String = "",
    val revKey: String = ""
)

private fun channelMapToList(map: String): List<String> {
    val values = map.split(",").map { it.trim() }.filter { it.isNotEmpty() }
    return List(CHANNEL_COUNT) { idx -> values.getOrNull(idx) ?: "none" }
}

private fun channelMapToString(values: List<String>): String =
    List(CHANNEL_COUNT) { idx -> values.getOrNull(idx)?.takeIf { it.isNotBlank() } ?: "none" }
        .joinToString(",")

private fun channelOutputValue(values: List<Int>, index: Int): Int =
    values.getOrElse(index) { if (index < 6) 1500 else 1000 }.coerceIn(800, 2200)

private fun channelLocksToList(lock: String): List<Boolean> {
    val values = lock.split(",").map { it.trim().lowercase() }.filter { it.isNotEmpty() }
    return List(CHANNEL_COUNT) { idx ->
        when (values.getOrNull(idx)) {
            "1", "true", "on", "yes" -> true
            else -> false
        }
    }
}

private fun channelLocksToString(values: List<Boolean>): String =
    List(CHANNEL_COUNT) { idx -> if (values.getOrNull(idx) == true) "1" else "0" }
        .joinToString(",")

private fun sourceSupportsLock(source: String): Boolean =
    source in setOf(
        "rec", "rth", "stop", "focus", "c1", "c2", "c3", "aircraft", "back", "btn",
        "up", "down", "left", "right"
    )

// 长按触发只对按键源有意义 (与自锁源集合一致)
private fun sourceSupportsLongPress(source: String): Boolean = sourceSupportsLock(source)

private fun responseSupportsSrcCfg(response: String): Boolean =
    Regex("\"src_cfg_names\"\\s*:").containsMatchIn(response)

private fun sanitizeChannelRange(min: Int, max: Int): Pair<Int, Int> {
    val a = min.coerceIn(800, 2200)
    val b = max.coerceIn(800, 2200)
    return if (a <= b) a to b else b to a
}

private fun sourceKeys(source: String): SourceKeys = when {
    source.matches(Regex("ch[1-6]")) -> {
        val n = source.removePrefix("ch")
        SourceKeys("st${n}_min", "st${n}_max", "st${n}_mid", "st${n}_rev")
    }
    source == "dial" -> SourceKeys("dial_min", "dial_max", "", "dial_rev")
    source == "mode" -> SourceKeys("mode_s", "mode_f", "mode_n", "")
    source == "shot" -> SourceKeys("shot_lo", "shot_hi", "shot_mid", "")
    source == "c12" -> SourceKeys("c12_0", "c12_3", "", "")
    source == "dir" -> SourceKeys("dir_0", "dir_5", "", "")
    source == "lr" -> SourceKeys("lr_0", "lr_5", "", "")
    source in setOf("rec", "rth", "stop", "focus", "c1", "c2", "c3", "aircraft", "back", "btn", "up", "down", "left", "right") ->
        SourceKeys("${source}_off", "${source}_on", "", "")
    else -> SourceKeys()
}

// 长按触发的 src_cfg key (按键源): rec→rec_lp
private fun sourceLpKey(source: String): String =
    if (sourceSupportsLongPress(source)) "${source}_lp" else ""

private fun sourceDisplayLabel(source: String): String = when (source) {
    "none" -> "无"
    "ch1" -> "J1"
    "ch2" -> "J2"
    "ch3" -> "J3"
    "ch4" -> "J4"
    "ch5" -> "J5"
    "ch6" -> "J6"
    "dial" -> "V1"
    "mode" -> "飞行模式"
    "rec" -> "REC"
    "rth" -> "RTH"
    "stop" -> "STOP"
    "focus" -> "FOCUS"
    "c1" -> "C1"
    "c2" -> "C2"
    "c3" -> "C3"
    "aircraft" -> "AIRCRAFT"
    "back" -> "BACK"
    "btn" -> "BTN"
    "up" -> "UP"
    "down" -> "DOWN"
    "left" -> "LEFT"
    "right" -> "RIGHT"
    "shot" -> "快门"
    "c12" -> "C1/C2"
    "dir" -> "方向键"
    "lr" -> "L1-R3 六档"
    else -> source
}

fun channelMapToListForTest(map: String): List<String> = channelMapToList(map)
fun channelMapToStringForTest(values: List<String>): String = channelMapToString(values)
fun channelOutputValueForTest(values: List<Int>, index: Int): Int = channelOutputValue(values, index)
fun channelLocksToListForTest(lock: String): List<Boolean> = channelLocksToList(lock)
fun channelLocksToStringForTest(values: List<Boolean>): String = channelLocksToString(values)
fun defaultChannelMapForTest(): String = DEFAULT_CHANNEL_MAP
fun responseSupportsSrcCfgForTest(response: String): Boolean = responseSupportsSrcCfg(response)
fun sanitizeChannelRangeForTest(min: Int, max: Int): IntArray {
    val r = sanitizeChannelRange(min, max)
    return intArrayOf(r.first, r.second)
}
fun sourceRangeKeysForTest(source: String): Array<String> {
    val keys = sourceKeys(source)
    return arrayOf(keys.minKey, keys.maxKey, keys.midKey, keys.revKey)
}
fun sourceDisplayLabelForTest(source: String): String = sourceDisplayLabel(source)

/** 输入源数值编辑行: rev 渲染为开关, 其余为数字输入框 */
@androidx.compose.runtime.Composable
private fun SrcCfgEditRow(row: SrcCfgRow, value: Int, onValue: (Int) -> Unit) {
    Row(modifier = Modifier.fillMaxWidth().padding(vertical = 1.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(row.label, fontSize = 9.sp, color = Color(0xFF64748B), modifier = Modifier.width(80.dp))
        if (row.rev) {
            Surface(color = if (value != 0) Color(0xFF0EA5E9) else Color(0xFF1E293B), shape = RoundedCornerShape(4.dp),
                onClick = { onValue(if (value != 0) 0 else 1) }) {
                Text(if (value != 0) "开" else "关", fontSize = 9.sp, fontWeight = FontWeight.Bold,
                    color = if (value != 0) Color.Black else Color(0xFF64748B),
                    modifier = Modifier.padding(horizontal = 12.dp, vertical = 4.dp))
            }
        } else {
            Box(modifier = Modifier.weight(1f).height(24.dp)
                .background(Color(0xFF0F172A), RoundedCornerShape(4.dp))
                .border(1.dp, Color(0xFF334155), RoundedCornerShape(4.dp))
                .padding(horizontal = 6.dp), contentAlignment = Alignment.CenterStart) {
                BasicTextField(
                    value = value.toString(),
                    onValueChange = { t ->
                        val digits = t.filter { it.isDigit() }.take(4)
                        onValue(digits.toIntOrNull() ?: 0)
                    },
                    singleLine = true,
                    textStyle = androidx.compose.ui.text.TextStyle(fontSize = 9.sp, color = Color(0xFF38BDF8)),
                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    modifier = Modifier.fillMaxWidth())
            }
        }
    }
}

/** 输入源数值折叠组 */
@androidx.compose.runtime.Composable
private fun SrcCfgGroup(name: String, rows: List<SrcCfgRow>, values: Map<String, Int>, onValue: (String, Int) -> Unit) {
    var open by remember { mutableStateOf(false) }
    Column(Modifier.fillMaxWidth().padding(bottom = 4.dp)) {
        Surface(color = Color(0xFF1E293B), shape = RoundedCornerShape(5.dp), onClick = { open = !open }) {
            Text("${if (open) "▼" else "▶"} $name", fontSize = 9.sp, fontWeight = FontWeight.Bold, color = Color(0xFF94A3B8),
                modifier = Modifier.padding(horizontal = 8.dp, vertical = 5.dp))
        }
        if (open) {
            Spacer(Modifier.height(3.dp))
            rows.forEach { row ->
                SrcCfgEditRow(row, values[row.key] ?: row.def, onValue = { onValue(row.key, it) })
            }
        }
    }
}

class MainActivity : ComponentActivity() {
    companion object {
        private const val TAG = "MainActivity"
        private const val USB_PERM_ACTION = "com.tunnathub.app.USB_PERM"
        // V3s 同线供电, 开机需 10-15s → 最多轮询 30 次 (每 2s = 60s)
        private const val USB_POLL_MAX = 30
        private const val SHIZUKU_PERMISSION_REQUEST_CODE = 20260829
    }
    private var usbDevice: UsbDevice? = null
    private var connectionState = "idle"

    private val usbReceiver = object : BroadcastReceiver() {
        override fun onReceive(ctx: Context, intent: Intent) {
            if (USB_PERM_ACTION != intent.action) return
            if (intent.getBooleanExtra(UsbManager.EXTRA_PERMISSION_GRANTED, false)) {
                connectionState = "connecting"
                requestVpn()
            }
        }
    }

    /** Shizuku 授权结果回调: 授权成功后重建 RC 融合, 让 getevent reader 从 adb 回退切到 Shizuku。 */
    private val shizukuPermissionListener = Shizuku.OnRequestPermissionResultListener { requestCode, grantResult ->
        if (requestCode == SHIZUKU_PERMISSION_REQUEST_CODE &&
            grantResult == android.content.pm.PackageManager.PERMISSION_GRANTED
        ) {
            AppLog.i(TAG, "Shizuku 授权成功, 重建 RC 融合切换 getevent reader")
            TunNatVpnService.requestRcFusionRestart()
        }
    }

    private val vpnLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == RESULT_OK) {
            startTunService()
            connectionState = "connected"
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        registerReceiver(usbReceiver, IntentFilter(USB_PERM_ACTION), Context.RECEIVER_NOT_EXPORTED)
        try { Shizuku.addRequestPermissionResultListener(shizukuPermissionListener) } catch (_: Exception) {}
        if (RcInputMode.fromPreferences(this) == RcInputMode.ANDROID_FUSION) {
            ensureShizukuPermission()
        }
        usbDevice = findUsbDevice()
        if (usbDevice != null) connectionState = "found"

        setContent {
            // ── Compose 内驱动 USB 轮询 + 自动连接 ──
            var polledDevice by remember { mutableStateOf<UsbDevice?>(usbDevice) }
            var pollState by remember { mutableStateOf(if (usbDevice != null) "found" else "scanning") }
            var pollCount by remember { mutableIntStateOf(0) }
            var autoConnected by remember { mutableStateOf(false) }

            // H-1: key 用 Unit 而非 pollState, 避免 118 行 pollState="found" 触发 LaunchedEffect 重启 → 重复 startAuthFlow
            LaunchedEffect(Unit) {
                val um = this@MainActivity.getSystemService(Context.USB_SERVICE) as UsbManager
                var count = 0
                while (count < USB_POLL_MAX && !autoConnected) {
                    count++
                    pollCount = count
                    kotlinx.coroutines.delay(2000)
                    val dev = findUsbDevice()
                    if (dev != null) {
                        usbDevice = dev
                        polledDevice = dev
                        pollState = "found"
                        // 权限授予后主动检测 (DJI RC 权限广播可能不触发, 轮询 hasPermission)
                        if (um.hasPermission(dev)) {
                            autoConnected = true
                            startAuthFlow()   // hasPermission=true → requestVpn
                            return@LaunchedEffect
                        } else {
                            // 请求权限 (弹窗)
                            startAuthFlow()
                            // 等权限授予 (轮询 hasPermission, 不依赖广播)
                            var permCount = 0
                            while (permCount < 5) {
                                delay(2000)
                                if (um.hasPermission(dev)) {
                                    autoConnected = true
                                    requestVpn()
                                    return@LaunchedEffect
                                }
                                permCount++
                            }
                        }
                    }
                }
                if (!autoConnected) pollState = "timeout"
            }

            TunNatHubApp(
                usbFound = polledDevice != null,
                connectionState = pollState,
                usbPollCount = pollCount,
                onVpnTap = {
                    if (TunNatVpnService.isRunningState.value) {
                        // VPN 正在运行 → 断开
                        stopTunService()
                    } else {
                        // VPN 未运行 → 尝试连接。
                        // 注意: 若服务进程还在但 USB 断开 (isRunning=false), 直接 startAuthFlow
                        // 可能因 onStartCommand 的 isStarted 残留走"强制重启", 这里先 stop 再 start 保证干净重启
                        if (TunNatVpnService.isStartedForUi) {
                            // 服务在但 USB 断了 → 重启服务强制重连
                            stopTunService()
                            Handler(Looper.getMainLooper()).postDelayed({
                                startAuthFlow()
                            }, 500)
                        } else if (usbDevice != null) {
                            startAuthFlow()
                        }
                    }
                },
                onReconnect = {
                    // 强制重建 VPN (网段变更/手动重连): 设标志让 onStartCommand 绕过"直接复用",
                    // 使新的 lan_subnet 路由生效 (否则复用不重建, 旧路由残留 → 摄像头网段不通)。
                    TunNatVpnService.forceRestartRequested = true
                    stopTunService()
                    Handler(Looper.getMainLooper()).postDelayed({
                        usbDevice = findUsbDevice()
                        if (usbDevice != null) startAuthFlow()
                    }, 1500)
                }
            )
        }

    }

    override fun onDestroy() {
        super.onDestroy()
        playerHolder.getAndSet(null)?.stop()
        try { unregisterReceiver(usbReceiver) } catch (_: Exception) {}
        try { Shizuku.removeRequestPermissionResultListener(shizukuPermissionListener) } catch (_: Exception) {}
    }

    /**
     * Shizuku 集成: 以 shell 身份执行 getevent 读高频摇杆 (替代 adbd 中转)。
     * 未连接 → Toast 提示, getevent 走 adb 回退; 已连接未授权 → 弹授权窗;
     * 已授权 → 服务重建融合时 geteventReaderFactory 自动切 Shizuku。
     */
    fun ensureShizukuPermission() {
        if (!Shizuku.pingBinder()) {
            Toast.makeText(this, "Shizuku 未连接, getevent 走 adb 回退", Toast.LENGTH_SHORT).show()
            return
        }
        if (Shizuku.checkSelfPermission() != 0) {
            Toast.makeText(this, "需要 Shizuku 权限以读取高频摇杆", Toast.LENGTH_SHORT).show()
            try { Shizuku.requestPermission(SHIZUKU_PERMISSION_REQUEST_CODE) } catch (_: Exception) {}
        }
    }

    private fun startAuthFlow() {
        val dev = usbDevice ?: return
        val um = getSystemService(USB_SERVICE) as UsbManager
        if (um.hasPermission(dev)) requestVpn()
        else {
            val pi = PendingIntent.getBroadcast(this, 0,
                Intent(USB_PERM_ACTION).setPackage(packageName),
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
            um.requestPermission(dev, pi)
        }
    }

    private fun requestVpn() {
        val intent = VpnService.prepare(this)
        if (intent != null) vpnLauncher.launch(intent)
        else startTunService()
    }

    private fun startTunService() {
        AppLog.i(TAG, "启动 VPN 服务")
        val i = Intent(this, TunNatVpnService::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) startForegroundService(i) else startService(i)
    }

    private fun stopTunService() {
        AppLog.i(TAG, "停止 VPN 服务")
        stopService(Intent(this, TunNatVpnService::class.java))
    }

    private fun findUsbDevice(): UsbDevice? {
        val um = getSystemService(USB_SERVICE) as UsbManager
        for ((_, d) in um.deviceList)
            if (d.vendorId == UsbBridge.USB_VID && d.productId == UsbBridge.USB_PID) return d
        return null
    }
}

// ═══════════════════════════════════════════════════════
// Tab 定义
// ═══════════════════════════════════════════════════════

private enum class Tab { VIDEO, REMOTE, RECEIVER, CONFIG }

// ═══════════════════════════════════════════════════════
// 顶层：状态栏 + 导航 + 内容区
// ═══════════════════════════════════════════════════════

/**
 * 接收机页 — 内嵌 ELRS Lua 参数界面 (mock 假数据 / 真 V3s crsf-bridge)
 */
@Composable
private fun LuaParamEmbed() {
    val ctx = LocalContext.current
    val activity = ctx as? ComponentActivity
    val controller = remember { com.tunnathub.app.crsf.LuaParamController(ctx) }
    var rows by remember { mutableStateOf<List<com.tunnathub.app.crsf.ParamRow>>(emptyList()) }
    var title by remember { mutableStateOf("ELRS") }
    var loading by remember { mutableStateOf(true) }
    var phase by remember { mutableStateOf("连接 V3s...") }
    var popupText by remember { mutableStateOf("") }

    LaunchedEffect(Unit) {
        delay(800)
        if (!controller.isLoading) loading = false
    }

    DisposableEffect(controller) {
        controller.onRowsChanged = {
            val newRows = controller.getRows()
            if (activity != null) activity.runOnUiThread { rows = newRows }
            else rows = newRows
        }
        controller.onTitleChanged = {
            if (activity != null) activity.runOnUiThread { title = it }
            else title = it
        }
        controller.onLoadingChanged = {
            if (activity != null) activity.runOnUiThread { loading = it }
            else loading = it
        }
        controller.onPhaseChanged = {
            if (activity != null) activity.runOnUiThread { phase = it }
            else phase = it
        }
        controller.onPopupChanged = {
            if (activity != null) activity.runOnUiThread { popupText = it }
            else popupText = it
        }
        // mock(模拟器) host 用 NAT 网关; 真机走 V3s eth0 IP 192.168.144.66 (USB隧道→tun_hub→eth0 INPUT)
        // 实测 (2026-08-16): eth0 INPUT 投递正常 (V3s INPUT policy ACCEPT, 144.66:8080 可访问)
        val v3sHost = if (com.tunnathub.app.crsf.LuaEngine.isEmulator()) "10.0.2.2" else "192.168.144.66"
        controller.start(v3sHost)
        onDispose {
            controller.onRowsChanged = null
            controller.onTitleChanged = null
            controller.onLoadingChanged = null
            controller.onPhaseChanged = null
            controller.onPopupChanged = null
            controller.stop()
        }
    }

    com.tunnathub.app.crsf.LuaParamScreen(
        rows = rows,
        isLoading = loading,
        loadingPhase = phase,
        popupText = popupText,
        title = title,
        onUp = { controller.up() },
        onDown = { controller.down() },
        onEnter = { controller.enter() },
        onExit = { controller.exit() },
        onReload = { controller.reload() }
    )
}

@Composable
fun TunNatHubApp(usbFound: Boolean, connectionState: String = "idle", usbPollCount: Int = 0, onVpnTap: () -> Unit, onReconnect: (() -> Unit)? = null) {
    val ctx = LocalContext.current
    val prefs = ctx.getSharedPreferences("tun_nat_hub", Context.MODE_PRIVATE)
    // 视频自动重连常量 (局部, 供 scheduleAutoReconnect 使用)
    // V3s 重启后链路重建 (web_server DNAT 重试 + USB gadget 稳定) 可能需 1-2 分钟,
    // 重连次数需足够覆盖该窗口, 否则链路刚就绪时 app 已放弃 → 手动点才恢复。
    val MAX_AUTO_RECONNECT = 20
    // 基础重连延迟: 第 n 次延迟 = min(3s * 2^n, 60s), 链路未稳时不急着重连, 避免反复失败
    val AUTO_RECONNECT_BASE_DELAY_MS = 3000L
    // 响应式订阅 VPN 运行状态: isRunningState 变化时触发重组,
    // 使下方 LaunchedEffect(vpnRunning) 在 VPN 启动后真正执行
    val vpnRunning by TunNatVpnService.isRunningState
    val serviceFusedRcData by TunNatVpnService.fusedRcDataState
    val serviceRcSourceStats by TunNatVpnService.fusedRcSourceStatsState
    var rcInputMode by remember { mutableStateOf(RcInputMode.fromPreferences(ctx)) }
    var selectedTab by remember { mutableStateOf(Tab.VIDEO) }

    fun fmtSize(bytes: Long): String = when {
        bytes > 1024 * 1024 -> " %.1fM".format(bytes / 1024f / 1024f)
        bytes > 1024 -> " %.0fK".format(bytes / 1024f)
        else -> " ${bytes}B"
    }
    fun jsonString(src: String, key: String): String? =
        Regex("\"$key\":\\s*\"([^\"]+)\"").find(src)?.groupValues?.get(1)
    fun jsonLong(src: String, key: String): Long? =
        Regex("\"$key\":\\s*(\\d+)").find(src)?.groupValues?.get(1)?.toLongOrNull()
    fun jsonInt(src: String, key: String, fallback: Int = 0): Int =
        Regex("\"$key\":\\s*(-?\\d+)").find(src)?.groupValues?.get(1)?.toIntOrNull() ?: fallback
    fun calcMbps(tx: Long, rx: Long, prevTx: Long, prevRx: Long, dtMs: Long): String {
        if (dtMs <= 0 || (prevTx == 0L && prevRx == 0L)) return "0.0"
        val bytes = (tx - prevTx).coerceAtLeast(0) + (rx - prevRx).coerceAtLeast(0)
        return "%.1f".format(bytes * 8.0 / dtMs / 1000.0)
    }

    // C-02: 协程 scope 随 composition 取消 — apiPost 使用, 避免 Activity 销毁后孤儿协程泄漏
    val apiScope = androidx.compose.runtime.rememberCoroutineScope()

    val savedUrl = prefs.getString("rtsp_url", "rtsp://192.168.144.31:554/stream1")
        ?: "rtsp://192.168.144.31:554/stream1"
    var rtspUrl by remember { mutableStateOf(savedUrl) }
    var isPlaying by remember { mutableStateOf(false) }
    var statusText by remember { mutableStateOf("") }
    var resolutionText by remember { mutableStateOf("") }
    var surfaceViewRef by remember { mutableStateOf<SurfaceView?>(null) }
    var glSurfaceRef by remember { mutableStateOf<com.tunnathub.app.video.GlLowLatencySurface?>(null) }
    // Surface 是否已就绪 (surfaceCreated 回调后为 true)。
    // 回前台时 SurfaceView 的 Surface 重建是异步的, 未就绪就播放会拿到已释放的 Surface
    // → render 线程 lockCanvas 每帧报 "Surface has already been released" → 画面卡死 (流量仍在跑)。
    var surfaceReady by remember { mutableStateOf(false) }
    // 切后台前是否正在播放: 用于回前台时区分"恢复之前正在播的" vs "从未主动播放过"。
    // 老大要求: 进 app 不要自动播放视频, 由用户手动点播放按钮。
    // 回前台只恢复"切后台前正在播的", 不自动启动从未播过的会话。
    var wasPlayingBeforePause by remember { mutableStateOf(false) }
    // 挂起标记: Surface 未就绪时收到了播放请求, 等 surfaceCreated 回调后再真正启动
    var pendingPlayAfterSurface by remember { mutableStateOf(false) }
    var playerRef by remember { mutableStateOf<RtspPlayerSession?>(null) }
    var autoReconnectCount by remember { mutableStateOf(0) }   // 自动重连计数
    var autoReconnectActive by remember { mutableStateOf(false) } // 自动重连开关(手动停止后关闭)
    // 函数引用 (打破播放回调→schedule→start→播放回调循环引用, 定义后赋值)
    lateinit var startPlaybackFn: () -> Unit
    lateinit var scheduleAutoReconnectFn: () -> Unit

    // ── 心跳状态 ──
    var hbDaemon by remember { mutableStateOf(false) }
    var hbTty by remember { mutableStateOf(false) }
    var hbTun by remember { mutableStateOf(false) }
    var hbCount by remember { mutableStateOf(0) }
    var hbBw by remember { mutableStateOf("0.0") }
    var hbTx by remember { mutableStateOf(0L) }
    var hbRx by remember { mutableStateOf(0L) }
    var v3sVersion by remember { mutableStateOf("") }   // V3s 固件版本 (来自 /api/heartbeat)

    // ── RC 遥控器状态 ──
    var rcConnected by remember { mutableStateOf(false) }
    var rcChs by remember { mutableStateOf(List(16) { 1500 }) }
    var rcRawChs by remember { mutableStateOf(List(6) { 0 }) }
    var rcMode by remember { mutableStateOf("?") }
    // RC 输出协议 (sbus/crsf): 全局共享, 决定侧边栏"接收机"tab 是否显示 (CRSF=ELRS 模式)
    var rcOutMode by remember { mutableStateOf("sbus") }
    // 非 CRSF (非 ELRS 模式) 时接收机 tab 隐藏, 若正停在接收机页则切回遥控页
    LaunchedEffect(rcOutMode, selectedTab) {
        if (rcOutMode != "crsf" && selectedTab == Tab.RECEIVER) selectedTab = Tab.REMOTE
    }
    var rcBtn by remember { mutableStateOf(0) }; var rcStop by remember { mutableStateOf(0) }
    var rcFocus by remember { mutableStateOf(0) }; var rcShot by remember { mutableStateOf(0) }
    var rcRec by remember { mutableStateOf(0) }; var rcRth by remember { mutableStateOf(0) }
    var rcC1 by remember { mutableStateOf(0) }; var rcC2 by remember { mutableStateOf(0) }
    var rcC3 by remember { mutableStateOf(0) }; var rcDial by remember { mutableStateOf(0) }
    var rcUp by remember { mutableStateOf(0) }; var rcDown by remember { mutableStateOf(0) }
    var rcLeft by remember { mutableStateOf(0) }; var rcRight by remember { mutableStateOf(0) }
    var rcAircraft by remember { mutableStateOf(0) }; var rcBack by remember { mutableStateOf(0) }
    var rcL1 by remember { mutableStateOf(0) }; var rcL2 by remember { mutableStateOf(0) }
    var rcL3 by remember { mutableStateOf(0) }; var rcR1 by remember { mutableStateOf(0) }
    var rcR2 by remember { mutableStateOf(0) }; var rcR3 by remember { mutableStateOf(0) }
    var rcType by remember { mutableStateOf("") }
    var v3sRcMsgCount by remember { mutableIntStateOf(0) }
    var v3sRcMsgHz by remember { mutableStateOf(0f) }
    val currentRcInputMode by rememberUpdatedState(rcInputMode)

    LaunchedEffect(vpnRunning) {
        var lastCount = v3sRcMsgCount
        var lastAt = System.currentTimeMillis()
        while (vpnRunning) {
            delay(1000L)
            val now = System.currentTimeMillis()
            val dtMs = (now - lastAt).coerceAtLeast(1L)
            val count = v3sRcMsgCount
            v3sRcMsgHz = ((count - lastCount).coerceAtLeast(0) * 1000f) / dtMs
            lastCount = count
            lastAt = now
        }
        v3sRcMsgHz = 0f
    }

    fun applyRcData(data: RcMsg.Data, type: String) {
        rcConnected = true
        // 防抖: RC-FUSION(本地融合) 与 RC(V3s回传) 双源交替更新, 相同数据跳过
        // 避免无意义重组导致遥控页通道条高频闪动 (值静止时不重组)
        if (data.chs == rcChs && data.rawChs == rcRawChs && data.mode == rcMode &&
            data.btn == rcBtn && data.stop == rcStop && data.focus == rcFocus &&
            data.shot == rcShot && data.rec == rcRec && data.rth == rcRth &&
            data.c1 == rcC1 && data.c2 == rcC2 && data.c3 == rcC3 && data.dial == rcDial &&
            data.up == rcUp && data.down == rcDown && data.left == rcLeft &&
            data.right == rcRight && data.aircraft == rcAircraft && data.back == rcBack &&
            data.l1 == rcL1 && data.l2 == rcL2 && data.l3 == rcL3 &&
            data.r1 == rcR1 && data.r2 == rcR2 && data.r3 == rcR3) {
            return
        }
        rcChs = rcChannelsForIncomingData(rcChs, data.chs, rcInputMode, type)
        rcRawChs = data.rawChs
        rcMode = data.mode
        rcBtn = data.btn; rcStop = data.stop
        rcFocus = data.focus; rcShot = data.shot
        rcRec = data.rec; rcRth = data.rth
        rcC1 = data.c1; rcC2 = data.c2
        rcC3 = data.c3; rcDial = data.dial
        rcUp = data.up; rcDown = data.down
        rcLeft = data.left; rcRight = data.right
        rcAircraft = data.aircraft; rcBack = data.back
        rcL1 = data.l1; rcL2 = data.l2; rcL3 = data.l3
        rcR1 = data.r1; rcR2 = data.r2; rcR3 = data.r3
        rcType = type
    }

    LaunchedEffect(serviceFusedRcData, rcInputMode) {
        if (rcInputMode == RcInputMode.ANDROID_FUSION) {
            serviceFusedRcData?.let { applyRcData(it, "RC-FUSION") }
        }
    }

    // ── 摄像头列表 ──
    data class CamInfo(val name: String, val url: String)
    var cameras by remember { mutableStateOf(listOf<CamInfo>()) }

    // ── LAN 网段 ──
    val savedLanSubnet = prefs.getString("lan_subnet", "192.168.144.0") ?: "192.168.144.0"
    val savedLanPrefix = prefs.getInt("lan_prefix", 24)
    var needVpnReconnect by remember { mutableStateOf(false) }

    // ── 解码器选择 ──
    val savedPlaybackEngine = remember { RtspPlaybackEngine.fromPref(prefs.getString("playback_engine", null)) }
    var playbackEngine by remember { mutableStateOf(savedPlaybackEngine) }
    val savedCodec = remember {
        val codec = prefs.getString("forced_codec", null)
        if (codec.isNullOrBlank() || codec == "auto") LowLatencyRtspPlayer.DEFAULT_H264_CODEC else codec
    }
    LaunchedEffect(Unit) {
        LowLatencyRtspPlayer.setForcedCodec(savedCodec)
        prefs.edit().putString("forced_codec", savedCodec).apply()
    }

    // 延迟测试
    var latencyText by remember { mutableStateOf("") }
    var testing by remember { mutableStateOf(false) }
    var codecBenchmarkRunning by remember { mutableStateOf(false) }
    var codecBenchmarkText by remember { mutableStateOf("") }
    var rtspUdpProbeRunning by remember { mutableStateOf(false) }
    var rtspUdpProbeText by remember { mutableStateOf("") }
    var rtcpFeedbackText by remember { mutableStateOf("") }
    var rtcpFeedbackRunning by remember { mutableStateOf(false) }
    var lastRtcpFeedbackAt by remember { mutableLongStateOf(0L) }
    // ── HTTP POST ──
    // C-02: 用 remember 的 apiScope (随 composition 取消), 避免每次调用创建孤儿协程
    fun apiPost(path: String, body: String, onResult: ((Boolean) -> Unit)? = null) {
        apiScope.launch(kotlinx.coroutines.Dispatchers.IO) {
            var ok = false
            try {
                val url = java.net.URL("http://192.168.144.66:8080$path")
                val conn = url.openConnection() as java.net.HttpURLConnection
                conn.connectTimeout = 3000; conn.readTimeout = 3000
                conn.doOutput = true; conn.requestMethod = "POST"
                conn.setRequestProperty("Content-Type", "application/json")
                try {
                    conn.outputStream.use { it.write(body.toByteArray()) }
                    // H-04: 消费响应, use{} 保证异常路径也关闭流
                    conn.inputStream.use { it.readBytes() }
                    ok = true
                } finally {
                    conn.disconnect()
                }
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (e: Exception) {
                android.util.Log.e("TunNatHub", "API POST $path 失败: ${e.javaClass.simpleName} ${e.message}")
            }
            onResult?.invoke(ok)
        }
    }

    // ── 心跳轮询 ──
    LaunchedEffect(vpnRunning) {
        if (!vpnRunning) { hbCount = 0; return@LaunchedEffect }
        var prevTx = hbTx
        var prevRx = hbRx
        var prevAt = System.currentTimeMillis()
        while (vpnRunning) {
            kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
                try {
                    val text = java.net.URL("http://192.168.144.66:8080/api/heartbeat").openConnection()
                        .apply { connectTimeout = 2000; readTimeout = 2000 }
                        .getInputStream().bufferedReader().readText()
                    val statsText = try {
                        java.net.URL("http://192.168.144.66:8080/api/stats").openConnection()
                            .apply { connectTimeout = 1500; readTimeout = 1500 }
                            .getInputStream().bufferedReader().readText()
                    } catch (_: Exception) { "" }
                    hbDaemon = text.contains("\"daemon\":true")
                    hbTty = text.contains("\"tty_ready\":true")
                    hbTun = text.contains("\"tun_up\":true")
                    jsonString(text, "version")?.let { if (it.isNotEmpty()) v3sVersion = it }
                    val tx = jsonLong(statsText, "tx_bytes") ?: jsonLong(text, "tx_bytes") ?: hbTx
                    val rx = jsonLong(statsText, "rx_bytes") ?: jsonLong(text, "rx_bytes") ?: hbRx
                    val apiBw = jsonString(text, "bandwidth_mbps") ?: jsonString(statsText, "bandwidth_mbps")
                    val nowMs = System.currentTimeMillis()
                    val fallbackBw = calcMbps(tx, rx, prevTx, prevRx, nowMs - prevAt)
                    hbBw = apiBw?.takeIf { it.isNotBlank() && it != "0.0" } ?: fallbackBw
                    hbTx = tx
                    hbRx = rx
                    prevTx = tx
                    prevRx = rx
                    prevAt = nowMs
                    hbCount++
                } catch (e: kotlinx.coroutines.CancellationException) {
                    throw e
                } catch (_: Exception) { hbDaemon = false; hbTty = false; hbTun = false }
            }
            kotlinx.coroutines.delay(1000)
        }
    }

    // ── 配置轮询 ──
    LaunchedEffect(vpnRunning) {
        if (!vpnRunning) return@LaunchedEffect
        kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
            try {
                val text = java.net.URL("http://192.168.144.66:8080/api/config").openConnection()
                    .apply { connectTimeout = 2000; readTimeout = 2000 }
                    .getInputStream().bufferedReader().readText()
                AppLog.d("TunNatHub", "获取 V3s 配置: OK (${text.length} bytes)")
                val camList = Regex("\"name\":\\s*\"([^\"]+)\"[^}]*\"url\":\\s*\"([^\"]+)\"").findAll(text).map {
                    CamInfo(it.groupValues[1], it.groupValues[2])
                }.toList()
                if (camList.isNotEmpty()) { cameras = camList; if (rtspUrl.isEmpty()) rtspUrl = camList[0].url }
                val lanMatch = Regex("\"lan_subnet\": \"(\\d+\\.\\d+\\.\\d+)\\.0/(\\d+)\"").find(text)
                if (lanMatch != null) {
                    val rs = "${lanMatch.groupValues[1]}.0"
                    val rp = lanMatch.groupValues[2].toInt()
                    if (rs != savedLanSubnet || rp != savedLanPrefix) {
                        prefs.edit().putString("lan_subnet", rs).putInt("lan_prefix", rp).apply()
                        needVpnReconnect = true
                        AppLog.w("TunNatHub", "网段不同步! V3s=$rs/$rp → 自动同步")
                    }
                }
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (_: Exception) {}
        }
    }

    // ── RC 遥控器数据: 直接收 UDP rcmsg (不经 HTTP) ──
    LaunchedEffect(vpnRunning) {
        if (!vpnRunning) return@LaunchedEffect
        kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
            try {
                // 打开受保护的 UDP socket (绑定 192.168.144.11:65530), 内核才投递入站包
                // H-02: 捕获局部 val, 避免 !! (sock 是 var, 并发可能被重赋值)
                val sock = TunNatVpnService.openProtectedPort(RcMsg.PORT)
                if (sock == null) {
                    rcConnected = false
                    return@withContext
                }
                sock.soTimeout = 100    // 让取消/重建时快速退出, 避免旧接收循环抢 65530 包
                val buf = ByteArray(256)
                val pkt = java.net.DatagramPacket(buf, buf.size)
                while (vpnRunning && currentCoroutineContext().isActive) {
                    try {
                        sock.receive(pkt)
                        val data = RcMsg.parse(pkt.data.copyOf(pkt.length))
                        if (data != null) {
                            v3sRcMsgCount++
                            // V3s 回传含按键映射后的实际 CH 输出 (CH7-16: rec→CH8, mode→CH7, dial→CH12 等, 固件 src_value 映射)。
                            if (currentRcInputMode == RcInputMode.V3S_RCMSG) {
                                applyRcData(data, "V3S-RCMSG")
                            } else {
                                // 安卓融合模式只更新 CH7-16, 摇杆 CH1-6 仍用本地融合即时。
                                rcConnected = true
                                rcChs = rcChannelsForIncomingData(rcChs, data.chs, currentRcInputMode, "V3S-RCMSG")
                            }
                        }
                    } catch (_: java.net.SocketTimeoutException) {
                        // 空闲超时, 继续等
                    } catch (_: java.io.IOException) {
                        // VPN 断开等: 结束
                        rcConnected = false
                        break
                    }
                }
            } catch (e: kotlinx.coroutines.CancellationException) {
                throw e
            } catch (_: Exception) {
                rcConnected = false
            } finally {
                // 不关闭 socket: 它是 protectPort 持有的锚定 socket, 由 VPN 服务管理
            }
        }
    }

    fun togglePlay() {
        if (isPlaying) {
            playerRef?.stop(); playerRef = null; isPlaying = false; statusText = "已停止"
            playerHolder.set(null)
            autoReconnectActive = false  // 手动停止 → 关闭自动重连
            pendingPlayAfterSurface = false  // 停止后不再等待 Surface, 防止 surfaceCreated 意外启动
        } else {
            autoReconnectActive = true   // 手动播放 → 开启自动重连
            startPlaybackFn()
        }
    }

    /** UDP_SELF 自建会话播放器的回调（复用低延迟播放器的 UI 逻辑，PLI 计数不同语义）。 */
    val udpPlayerCallback = remember {
        object : UdpRtspPlayer.Callback {
            private val mainHandler = Handler(ctx.mainLooper)

            override fun onVideoDisplayed(codecName: String) {
                mainHandler.post {
                    val ts = codecName.split(".").last().take(25)
                    statusText = "播放中 [UDP:$ts]"
                    isPlaying = true
                    autoReconnectCount = 0
                    AppLog.i("Player", "自建UDP低延迟硬解: $codecName")
                }
            }

            override fun onVideoSize(width: Int, height: Int) {
                mainHandler.post { resolutionText = "${width}x${height}" }
            }

            override fun onTimeout() {
                mainHandler.post {
                    statusText = "连接超时"
                    isPlaying = false
                    scheduleAutoReconnectFn()
                }
            }

            override fun onUnsupportedVideo() {
                mainHandler.post {
                    statusText = "编码不支持"
                    isPlaying = false
                    scheduleAutoReconnectFn()
                }
            }

            override fun onError(message: String?, error: Throwable?) {
                mainHandler.post {
                    statusText = "播放错误"
                    isPlaying = false
                    AppLog.e("Player", "UDP播放错误: ${message ?: error?.javaClass?.simpleName ?: "unknown"}")
                    scheduleAutoReconnectFn()
                }
            }

            override fun onWaitingKeyFrame(elapsedMs: Long, pliSent: Int) {
                mainHandler.post {
                    statusText = "Waiting IDR ${elapsedMs}ms, PLI=$pliSent"
                    isPlaying = true
                }
            }

            override fun onRtpDiag(message: String) {
                AppLog.i("UdpRtspPlayer", message)
            }
        }
    }

    // ── 切后台/回前台: SurfaceView 的 Surface 在切后台销毁, 渲染线程 lockCanvas 会卡死
    // ("Surface was already locked")。切后台停止播放, 回前台自动恢复。
    val lifecycleOwner = androidx.compose.ui.platform.LocalLifecycleOwner.current
    androidx.compose.runtime.DisposableEffect(lifecycleOwner) {
        val observer = androidx.lifecycle.LifecycleEventObserver { _, event ->
            when (event) {
                androidx.lifecycle.Lifecycle.Event.ON_PAUSE -> {
                    // 记录切后台前是否正在播 (供回前台判断是否恢复)。先记录再 stop。
                    wasPlayingBeforePause = isPlaying
                    if (isPlaying) {
                        playerHolder.getAndSet(null)?.stop()
                        playerRef = null
                        isPlaying = false
                        statusText = "已停止 (切后台)"
                        AppLog.i("Player", "切后台, 停止播放 (Surface 失效)")
                    }
                }
                androidx.lifecycle.Lifecycle.Event.ON_RESUME -> {
                    // 回前台: 只在"切后台前正在播"时才恢复播放, 不自动启动从未主动播过的会话。
                    // (老大要求: 进 app 不要自动播放视频, 由用户手动点播放按钮)
                    if (wasPlayingBeforePause && vpnRunning && !isPlaying && rtspUrl.isNotBlank() && surfaceViewRef != null) {
                        startPlaybackFn()
                    }
                }
                else -> {}
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }

    // ── 自动播放: 已禁用。老大要求进 app 不要自动播放视频, 由用户手动点播放按钮触发。
    // 原逻辑: VPN 连上且未在播放时自动播放保存的 RTSP, 冷启动/链路重建时偶发
    // not-linked/摄像头会话冲突 → 需要手动点一次, 现改为彻底不自动播, 消除这些时序问题。
    // 挂起标记 (pendingPlayAfterSurface) 仍由手动播放/回前台恢复时使用, 这里保持无操作。

    fun autoSyncSubnet(url: String) {
        val ipMatch = Regex("rtsp://(\\d+\\.\\d+\\.\\d+)\\.\\d+").find(url) ?: return
        val ns = "${ipMatch.groupValues[1]}.0"
        if (ns != (prefs.getString("lan_subnet", "192.168.144.0") ?: "192.168.144.0")) {
            prefs.edit().putString("lan_subnet", ns).putInt("lan_prefix", 24).apply()
            needVpnReconnect = true
            AppLog.w("TunNatHub", "网段自动同步 → $ns")
        }
    }

    /** 启动 RTSP 播放 (playerCallback/autoSyncSubnet 已定义, 无前向引用) */
    fun doStartPlayback() {
        // QGC_SOFTWARE 用 GLSurfaceView（glSurfaceRef），其他引擎用 SurfaceView
        val sv = surfaceViewRef
        val glSrf = glSurfaceRef
        if (playbackEngine != RtspPlaybackEngine.QGC_SOFTWARE && sv == null) return
        if (playbackEngine == RtspPlaybackEngine.QGC_SOFTWARE && glSrf == null) return
        // Surface 未就绪 (切后台回前台时 Surface 重建是异步的): 挂起等待 surfaceCreated 回调,
        // 避免用已释放的 Surface 创建播放器 → render 每帧 "Surface has already been released" 画面卡死。
        if (playbackEngine != RtspPlaybackEngine.QGC_SOFTWARE && !surfaceReady) {
            pendingPlayAfterSurface = true
            AppLog.w("Player", "播放请求挂起: Surface 未就绪, 等 surfaceCreated")
            return
        }
        // H2: 先释放旧播放器, 避免自动重连时 native 解码器泄漏。
        // 注意: 只用 playerHolder 做权威清理 (与 onDestroy 一致), 避免对同一实例双重 stop 触发 native 崩溃
        playerHolder.getAndSet(null)?.stop()
        playerRef = null
        try {
            prefs.edit().putString("rtsp_url", rtspUrl).apply()
            autoSyncSubnet(rtspUrl)
            val session: RtspPlayerSession = when (playbackEngine) {
                RtspPlaybackEngine.MEDIA3_UDP -> {
                val media3 = Media3RtspProbePlayer(ctx, sv!!.holder.surface, object : Media3RtspProbePlayer.Callback {
                    override fun onVideoDisplayed() {
                        Handler(Looper.getMainLooper()).post {
                            statusText = "播放中 [Media3]"
                            isPlaying = true
                            autoReconnectCount = 0
                            AppLog.i("Player", "Media3 RTSP首帧显示")
                        }
                    }

                    override fun onError(message: String?) {
                        Handler(Looper.getMainLooper()).post {
                            statusText = "Media3播放错误"
                            isPlaying = false
                            AppLog.e("Player", "Media3 RTSP错误: ${message ?: "unknown"}")
                            scheduleAutoReconnectFn()
                        }
                    }
                })
                media3.start(rtspUrl)
                media3
                }
                RtspPlaybackEngine.QGC_SOFTWARE -> {
                    val softwareCodec = LowLatencyRtspPlayer.selectSoftwareH264CodecName()
                    if (softwareCodec.isNullOrBlank()) {
                        statusText = "未找到软件H264解码器"
                        AppLog.e("Player", "QGC-style start failed: no software h264 decoder")
                        scheduleAutoReconnectFn()
                        return
                    }
                    // QGC 风格：GL 渲染绕开 SurfaceView 队列。glSurfaceRef 在 UI factory 里创建。
                    val glSrf = glSurfaceRef
                    val udp = if (glSrf != null) {
                        UdpRtspPlayer(ctx, glSrf.getSurface(), udpPlayerCallback, softwareCodec, "QGC_SOFTWARE", glSrf)
                    } else {
                        UdpRtspPlayer(ctx, glSrf?.getSurface() ?: sv?.holder?.surface, udpPlayerCallback, softwareCodec, "QGC_SOFTWARE")
                    }
                    val rc = udp.start(rtspUrl)
                    if (rc != 0) {
                        statusText = "QGC风格播放启动失败"
                        AppLog.e("Player", "QGC-style UdpRtspPlayer start 失败 rc=$rc")
                        playerHolder.set(null)
                        scheduleAutoReconnectFn()
                        return
                    }
                    AppLog.i("Player", "QGC-style software decoder: $softwareCodec")
                    udp
                }
                RtspPlaybackEngine.UDP_SELF -> {
                // 自建 UDP 会话 + PLI 求关键帧
                val udp = UdpRtspPlayer(ctx, sv?.holder?.surface, udpPlayerCallback)
                val rc = udp.start(rtspUrl)
                if (rc != 0) {
                    statusText = "UDP播放启动失败"
                    AppLog.e("Player", "UdpRtspPlayer start 失败 rc=$rc")
                    playerHolder.set(null)
                    scheduleAutoReconnectFn()
                    return
                }
                udp
                }
                RtspPlaybackEngine.GST_QGC -> {
                    // GStreamer 引擎（参考 QGC GstVideoReceiver 逻辑）
                    val gst = com.tunnathub.app.video.GstQgcPlayer(
                        ctx, sv?.holder?.surface, object : com.tunnathub.app.video.GstQgcPlayer.Callback {
                            override fun onVideoDisplayed(decoderName: String) {
                                Handler(Looper.getMainLooper()).post {
                                    statusText = "播放中 [GStreamer:$decoderName]"
                                    isPlaying = true
                                    autoReconnectCount = 0
                                    AppLog.i("Player", "GStreamer 首帧: $decoderName")
                                }
                            }
                            override fun onVideoSize(width: Int, height: Int) {
                                Handler(Looper.getMainLooper()).post { resolutionText = "${width}x${height}" }
                            }
                            override fun onTimeout() {
                                Handler(Looper.getMainLooper()).post { statusText = "连接超时"; isPlaying = false; scheduleAutoReconnectFn() }
                            }
                            override fun onError(message: String?, error: Throwable?) {
                                Handler(Looper.getMainLooper()).post {
                                    statusText = "GStreamer播放错误"
                                    isPlaying = false
                                    AppLog.e("Player", "GStreamer错误: ${message ?: error?.javaClass?.simpleName}")
                                    scheduleAutoReconnectFn()
                                }
                            }
                            override fun onDecoderChanged(decoderName: String) {
                                AppLog.i("Player", "GStreamer 解码器: $decoderName")
                            }
                        }, rtspUrl
                    )
                    val rc = gst.start()
                    if (rc != 0) {
                        statusText = "GStreamer播放启动失败"
                        AppLog.e("Player", "GstQgcPlayer start 失败 rc=$rc")
                        playerHolder.set(null)
                        scheduleAutoReconnectFn()
                        return
                    }
                    gst
                }
            }
            playerRef = session; isPlaying = true; statusText = "连接中..."
            playerHolder.set(session)
        } catch (e: Exception) { Log.e("TunNatHub", "播放失败", e); statusText = "播放失败" }
    }

    fun formatBenchSnapshot(rank: Int, snapshot: BenchmarkStats.Snapshot, error: String?): String {
        val err = error ?: snapshot.error
        val prefix = if (rank > 0) "${rank}. " else ""
        val suffix = if (err.isNullOrBlank()) "" else " err=$err"
        return prefix + snapshot.codecName +
            " first=${snapshot.firstFrameMs}ms" +
            " dec=${snapshot.decodeAvgMs}/${snapshot.decodeP50Ms}/${snapshot.decodeP95Ms}ms" +
            " cb=${snapshot.callbackToInputAvgMs}/${snapshot.callbackToInputP95Ms}ms" +
            " rx=${snapshot.framesReceived}" +
            " in=${snapshot.inputQueued}" +
            " noIn=${snapshot.inputUnavailable}" +
            " frames=${snapshot.outputRendered}" +
            " drop=${snapshot.inputDropped}" + suffix
    }

    fun doRunCodecBenchmark() {
        val sv = surfaceViewRef ?: run {
            codecBenchmarkText = "Surface 未就绪"
            return
        }
        if (codecBenchmarkRunning) return
        val url = rtspUrl
        codecBenchmarkRunning = true
        codecBenchmarkText = "准备 1min/decoder 测试..."
        apiScope.launch(kotlinx.coroutines.Dispatchers.IO) {
            val originalCodec = LowLatencyRtspPlayer.getForcedCodec()
            val candidates = (listOf("auto") + LowLatencyRtspPlayer.listAvailableDecoders("video/avc")).distinct()
            val results = mutableListOf<Pair<BenchmarkStats.Snapshot, String?>>()
            withContext(kotlinx.coroutines.Dispatchers.Main) {
                autoReconnectActive = false
                playerHolder.getAndSet(null)?.stop()
                playerRef = null
                isPlaying = false
                statusText = "解码器测试中..."
            }
            try {
                candidates.forEachIndexed { index, codecName ->
                    withContext(kotlinx.coroutines.Dispatchers.Main) {
                        codecBenchmarkText = "(${index + 1}/${candidates.size}) 测试 $codecName"
                    }
                    LowLatencyRtspPlayer.setForcedCodec(codecName)
                    val firstFrame = java.util.concurrent.CountDownLatch(1)
                    val errorRef = java.util.concurrent.atomic.AtomicReference<String?>(null)
                    val callback = object : UdpRtspPlayer.Callback {
                        override fun onVideoDisplayed(codecName: String) {
                            firstFrame.countDown()
                        }

                        override fun onVideoSize(width: Int, height: Int) {}

                        override fun onTimeout() {
                            errorRef.compareAndSet(null, "timeout")
                            firstFrame.countDown()
                        }

                        override fun onUnsupportedVideo() {
                            errorRef.compareAndSet(null, "unsupported")
                            firstFrame.countDown()
                        }

                        override fun onError(message: String?, error: Throwable?) {
                            errorRef.compareAndSet(null, message ?: error?.javaClass?.simpleName ?: "error")
                            firstFrame.countDown()
                        }
                    }
                    val testPlayer = UdpRtspPlayer(ctx, sv?.holder?.surface, callback)
                    try {
                        testPlayer.start(url)
                        val displayed = firstFrame.await(120, java.util.concurrent.TimeUnit.SECONDS)
                        if (displayed && errorRef.get() == null) {
                            Thread.sleep(60_000)
                        } else {
                            Thread.sleep(1000)
                        }
                    } catch (e: Exception) {
                        errorRef.compareAndSet(null, e.javaClass.simpleName)
                    } finally {
                        val snapshot = testPlayer.snapshotStats()
                        testPlayer.stop()
                        results.add(snapshot to errorRef.get())
                        val live = results.mapIndexed { i, item -> formatBenchSnapshot(i + 1, item.first, item.second) }
                            .joinToString("\n")
                        withContext(kotlinx.coroutines.Dispatchers.Main) {
                            codecBenchmarkText = live
                        }
                    }
                }
            } finally {
                LowLatencyRtspPlayer.setForcedCodec(originalCodec)
                withContext(kotlinx.coroutines.Dispatchers.Main) {
                    codecBenchmarkRunning = false
                    val ranked = results.sortedWith(
                        compareBy<Pair<BenchmarkStats.Snapshot, String?>> { it.second != null || it.first.firstFrameMs < 0 }
                            .thenBy { it.first.firstFrameMs }
                            .thenBy { it.first.decodeP95Ms }
                    )
                    codecBenchmarkText = ranked.mapIndexed { i, item -> formatBenchSnapshot(i + 1, item.first, item.second) }
                        .joinToString("\n")
                    statusText = "解码器测试完成"
                    AppLog.i("PlayerBench", "解码器测试完成\n$codecBenchmarkText")
                }
            }
        }
    }

    /** 自动重连: 播放失败后延迟重试 (限次, 手动停止后不触发) */
    fun doRunRtspUdpProbe() {
        if (rtspUdpProbeRunning || !vpnRunning) return
        val url = rtspUrl
        rtspUdpProbeRunning = true
        rtspUdpProbeText = "RTSP UDP 探测中..."
        AppLog.i("RtspUdpProbe", "start $url")
        apiScope.launch(kotlinx.coroutines.Dispatchers.IO) {
            val normal = RtspUdpProbe.run(url, 5)
            val protectedTun = RtspUdpProbe.runProtectedTun(url, 5)
            val text = normal.toDisplayString() + "\n\n" + protectedTun.toDisplayString()
            AppLog.i("RtspUdpProbe", text)
            withContext(kotlinx.coroutines.Dispatchers.Main) {
                rtspUdpProbeText = text
                rtspUdpProbeRunning = false
            }
        }
    }

    fun doScheduleReconnect() {
        if (!autoReconnectActive) return                     // 手动停止 → 不重连
        if (isPlaying) return                                // 已在播 → 不重连
        // VPN 已断 → 链路不存在, 不重连 (等 VPN 重新连上后自动播放会触发)
        if (!vpnRunning) return
        if (autoReconnectCount >= MAX_AUTO_RECONNECT) {      // 达到上限 → 停止 (不再手动点)
            statusText = "自动重连已达上限, 请手动重试"
            AppLog.w("Player", "自动重连达上限 ($autoReconnectCount)")
            playerHolder.getAndSet(null)?.stop()
            playerRef = null
            isPlaying = false
            return
        }
        autoReconnectCount++
        // 指数退避: 第 n 次延迟 = min(3s * 2^n, 60s)。链路重建期 (V3s 重启) 前几次用短间隔,
        // 后面拉长, 覆盖 DNAT 重试 + USB 稳定的完整窗口, 链路就绪后自动连上。
        val delay = minOf(AUTO_RECONNECT_BASE_DELAY_MS * (1L shl autoReconnectCount), 60_000L)
        AppLog.i("Player", "自动重连 (${autoReconnectCount}/$MAX_AUTO_RECONNECT) ${delay}ms后")
        Handler(Looper.getMainLooper()).postDelayed({
            if (autoReconnectActive && !isPlaying && surfaceViewRef != null && vpnRunning) {
                startPlaybackFn()
            }
        }, delay)
    }

    // 函数引用赋值 (打破循环引用)
    startPlaybackFn = { doStartPlayback() }
    scheduleAutoReconnectFn = { doScheduleReconnect() }

    @Composable
    fun RcPanelContent() {
        fun sbusPct(v: Int): Float = ((v - 1000f) / (2000f - 1000f)).coerceIn(0f, 1f)

        @Composable
        fun StatusChip(label: String, value: String, active: Boolean, modifier: Modifier = Modifier) {
            Surface(color = if (active) Color(0xFF14532D) else Color(0xFF1E293B), shape = RoundedCornerShape(5.dp), modifier = modifier) {
                Row(
                    modifier = Modifier.fillMaxWidth().padding(horizontal = 6.dp, vertical = 3.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Text(label, fontSize = 9.sp, color = Color(0xFF94A3B8), maxLines = 1)
                    Text(value, fontSize = 10.sp, color = if (active) Color(0xFF22C55E) else Color(0xFFE2E8F0), fontFamily = androidx.compose.ui.text.font.FontFamily.Monospace, maxLines = 1)
                }
            }
        }

        @Composable
        fun ChannelBar(label: String, value: Int, raw: Int? = null, modifier: Modifier = Modifier) {
            val pct = sbusPct(value)
            val centered = kotlin.math.abs(value - 1500) <= 20
            val col = when {
                centered -> Color(0xFF22C55E)
                value > 1500 -> Color(0xFF38BDF8)
                else -> Color(0xFFF59E0B)
            }
            Row(modifier = modifier.padding(vertical = 2.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(label, fontSize = 10.sp, color = Color(0xFF94A3B8), modifier = Modifier.width(34.dp))
                Box(modifier = Modifier.weight(1f).height(12.dp).background(Color(0xFF1E293B), RoundedCornerShape(4.dp))) {
                    Box(modifier = Modifier.fillMaxWidth(pct).fillMaxHeight().background(col, RoundedCornerShape(4.dp)))
                    Box(modifier = Modifier.align(Alignment.Center).width(2.dp).fillMaxHeight().background(Color(0xAAE2E8F0)))
                }
                Text(
                    text = if (raw != null) "$value/$raw" else value.toString(),
                    fontSize = 10.sp,
                    fontFamily = androidx.compose.ui.text.font.FontFamily.Monospace,
                    color = Color(0xFFE2E8F0),
                    modifier = Modifier.width(if (raw != null) 72.dp else 46.dp).padding(start = 6.dp)
                )
            }
        }

        @Composable
        fun ModeSwitch(mode: String) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                listOf("S", "N", "F").forEach { pos ->
                    Surface(
                        color = if (mode == pos) Color(0xFF0EA5E9) else Color(0xFF1E293B),
                        shape = RoundedCornerShape(5.dp)
                    ) {
                        Text(pos, fontSize = 10.sp, fontWeight = FontWeight.Bold, color = if (mode == pos) Color.Black else Color(0xFF64748B), modifier = Modifier.padding(horizontal = 12.dp, vertical = 4.dp))
                    }
                }
            }
        }

        @Composable
        fun SbusChannelGrid() {
            val channels = (1..16).map { ch ->
                Triple("CH$ch", rcChs.getOrElse(ch - 1) { if (ch <= 6) 1500 else 1000 }, rcRawChs.getOrNull(ch - 1))
            }
            for (rowStart in channels.indices step 2) {
                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    channels.drop(rowStart).take(2).forEach { (label, value, raw) ->
                        ChannelBar(label, value, raw, modifier = Modifier.weight(1f))
                    }
                    if (rowStart + 1 >= channels.size) Spacer(modifier = Modifier.weight(1f))
                }
                Spacer(Modifier.height(2.dp))
            }
        }

        @Composable
        fun ButtonStatusGrid() {
            // 紧凑 4 列网格: 去掉分组标题, 12 个按键/拨轮 chip 密排 (方向键在 DpadStatus 单独展示)
            val items = listOf(
                "C1" to rcC1, "C2" to rcC2, "C3" to rcC3, "REC" to rcRec,
                "RTH" to rcRth, "STOP" to rcStop, "BACK" to rcBack, "FOCUS" to rcFocus,
                "SHOT" to rcShot, "DIAL" to rcDial, "BTN" to rcBtn, "AIR" to rcAircraft,
                "L1" to rcL1, "L2" to rcL2, "L3" to rcL3,
                "R1" to rcR1, "R2" to rcR2, "R3" to rcR3,
            )
            items.chunked(4).forEach { row ->
                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    row.forEach { (name, value) ->
                        Box(modifier = Modifier.weight(1f)) {
                            // DIAL 拨轮显示数值, 其余按键显示 ON/OFF (激活态高亮)
                            val v = if (name == "DIAL") value.takeIf { it != 0 }?.toString() ?: "0"
                                    else if (value != 0) "ON" else "OFF"
                            StatusChip(name, v, value != 0)
                        }
                    }
                    repeat(4 - row.size) { Spacer(Modifier.weight(1f)) }
                }
                Spacer(Modifier.height(4.dp))
            }
        }

        @Composable
        fun DpadStatus() {
            @Composable
            fun Pad(label: String, active: Boolean, modifier: Modifier = Modifier) {
                Surface(color = if (active) Color(0xFF14532D) else Color(0xFF1E293B), shape = RoundedCornerShape(5.dp), modifier = modifier.height(22.dp)) {
                    Box(contentAlignment = Alignment.Center, modifier = Modifier.fillMaxSize()) {
                        Text(label, fontSize = 10.sp, fontWeight = FontWeight.Bold, color = if (active) Color(0xFF22C55E) else Color(0xFF64748B))
                    }
                }
            }
            Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.fillMaxWidth()) {
                Row(modifier = Modifier.fillMaxWidth()) {
                    Spacer(Modifier.weight(1f))
                    Pad("UP", rcUp != 0, Modifier.weight(1f))
                    Spacer(Modifier.weight(1f))
                }
                Spacer(Modifier.height(3.dp))
                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    Pad("LEFT", rcLeft != 0, Modifier.weight(1f))
                    Pad("BTN", rcBtn != 0, Modifier.weight(1f))
                    Pad("RIGHT", rcRight != 0, Modifier.weight(1f))
                }
                Spacer(Modifier.height(3.dp))
                Row(modifier = Modifier.fillMaxWidth()) {
                    Spacer(Modifier.weight(1f))
                    Pad("DOWN", rcDown != 0, Modifier.weight(1f))
                    Spacer(Modifier.weight(1f))
                }
            }
        }

        // ── 通道设置工作台: 参考 F20 内容结构, 保持 TUN_NAT_HUB 暗色风格 ──
        @Composable
        fun RemoteChannelConfig() {
            var roBaud by remember { mutableStateOf("auto") }
            var roPreset by remember { mutableStateOf("default") }
            var roMap by remember { mutableStateOf("") }
            var roLocks by remember { mutableStateOf(channelLocksToString(emptyList())) }
            var roSources by remember { mutableStateOf(listOf<String>()) }
            var srcCfg by remember { mutableStateOf(SRC_CFG_GROUPS.flatMap { it.second }.associate { it.key to it.def }) }
            var srcCfgLoaded by remember { mutableStateOf(false) }
            var selectedSourceChannel by remember { mutableStateOf<Int?>(null) }
            var advancedExpanded by remember { mutableStateOf(false) }
            var roMsg by remember { mutableStateOf("") }
            var roReload by remember { mutableStateOf(0) }
            var roSbusStd by remember { mutableStateOf(true) }
            var loaded by remember { mutableStateOf(false) }

            LaunchedEffect(vpnRunning, roReload) {
                if (!vpnRunning) return@LaunchedEffect
                roMsg = "读取中..."
                val res = withContext(Dispatchers.IO) {
                    try {
                        java.net.URL("http://192.168.144.66:8080/api/rc/output").openConnection()
                            .apply { connectTimeout = 3000; readTimeout = 3000 }
                            .getInputStream().bufferedReader().readText()
                    } catch (e: Exception) { "" }
                }
                if (res.isNotEmpty()) {
                    rcOutMode = jsonString(res, "mode") ?: "sbus"
                    roBaud = jsonString(res, "baud") ?: "auto"
                    roPreset = jsonString(res, "map_preset") ?: "default"
                    roMap = channelMapToString(channelMapToList(jsonString(res, "map") ?: ""))
                    roLocks = channelLocksToString(channelLocksToList(jsonString(res, "lock") ?: ""))
                    roSources = (jsonString(res, "sources") ?: "").split(",").filter { it.isNotEmpty() }
                    roSbusStd = !Regex("\"sbus_std\"\\s*:\\s*false").containsMatchIn(res)
                    val supportsSrcCfg = responseSupportsSrcCfg(res)
                    srcCfgLoaded = supportsSrcCfg
                    if (supportsSrcCfg) {
                        SRC_CFG_GROUPS.flatMap { it.second }.forEach { row ->
                            srcCfg = srcCfg + (row.key to jsonInt(res, row.key, row.def))
                        }
                    }
                    roMsg = "已读取配置"
                    loaded = true
                } else {
                    roMsg = "读取失败, 点刷新重试"
                }
            }

            @Composable
            fun WorkbenchButton(label: String, active: Boolean = false, modifier: Modifier = Modifier, onClick: () -> Unit) {
                Surface(
                    color = if (active) Color(0xFF0EA5E9) else Color(0xFF1E293B),
                    shape = RoundedCornerShape(6.dp),
                    border = androidx.compose.foundation.BorderStroke(1.dp, if (active) Color(0xFF38BDF8) else Color(0xFF334155)),
                    onClick = onClick,
                    modifier = modifier.height(30.dp)
                ) {
                    Box(contentAlignment = Alignment.Center, modifier = Modifier.fillMaxSize().padding(horizontal = 8.dp)) {
                        Text(label, fontSize = 10.sp, fontWeight = FontWeight.Bold, color = if (active) Color.Black else Color(0xFFE2E8F0), maxLines = 1, overflow = TextOverflow.Ellipsis)
                    }
                }
            }

            @Composable
            fun ChannelScale(value: Int, modifier: Modifier = Modifier) {
                val pct = ((value - 800).coerceIn(0, 1400) / 1400f)
                Box(modifier = modifier.height(30.dp)) {
                    Box(modifier = Modifier.align(Alignment.Center).fillMaxWidth().height(4.dp).background(Color(0xFF334155), RoundedCornerShape(2.dp)))
                    Box(modifier = Modifier.align(Alignment.CenterStart).fillMaxWidth(pct).height(4.dp).background(Color(0xFF0EA5E9), RoundedCornerShape(2.dp)))
                    // 值气泡: 中心跟随 pct 但不裁剪 — 低端点 (如 900→7%) 也完整显示
                    androidx.compose.foundation.layout.BoxWithConstraints(modifier = Modifier.fillMaxWidth().height(20.dp)) {
                        val density = androidx.compose.ui.platform.LocalDensity.current
                        val trackPx = constraints.maxWidth.toFloat()
                        val bubblePx = with(density) { 34.dp.toPx() }   // 约 3-4 位数字标签宽 + padding
                        val centerPx = (pct * trackPx).coerceIn(bubblePx / 2f, (trackPx - bubblePx / 2f).coerceAtLeast(bubblePx / 2f))
                        Box(
                            modifier = Modifier.offset(x = with(density) { (centerPx - bubblePx / 2f).toDp() })
                                .background(Color(0xFF0369A1), RoundedCornerShape(3.dp))
                                .padding(horizontal = 5.dp, vertical = 1.dp)
                        ) {
                            Text("$value", fontSize = 10.sp, fontWeight = FontWeight.Bold, color = Color.White, maxLines = 1)
                        }
                    }
                    if (value !in 800..2200) {
                        Text("$value", fontSize = 10.sp, fontWeight = FontWeight.Bold, color = Color.White)
                    }
                }
            }

            @Composable
            fun RangeEditor(source: String, values: Map<String, Int>, enabled: Boolean, onValue: (String, Int) -> Unit) {
                if (!enabled) {
                    Text("固件不支持", fontSize = 9.sp, color = Color(0xFF475569), modifier = Modifier.width(128.dp))
                    return
                }
                val keys = sourceKeys(source)
                if (keys.minKey.isEmpty() || keys.maxKey.isEmpty()) {
                    Text("不可调", fontSize = 9.sp, color = Color(0xFF475569), modifier = Modifier.width(128.dp))
                    return
                }
                val minVal = values[keys.minKey] ?: 1000
                val maxVal = values[keys.maxKey] ?: 2000
                var minText by remember(source, minVal) { mutableStateOf(minVal.toString()) }
                var maxText by remember(source, maxVal) { mutableStateOf(maxVal.toString()) }
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp), verticalAlignment = Alignment.CenterVertically, modifier = Modifier.width(128.dp)) {
                    BasicTextField(
                        value = minText,
                        onValueChange = { txt ->
                            minText = txt.filter { it.isDigit() }.take(4)
                            minText.toIntOrNull()?.let { v ->
                                val r = sanitizeChannelRange(v, maxVal)
                                onValue(keys.minKey, r.first)
                                onValue(keys.maxKey, r.second)
                            }
                        },
                        singleLine = true,
                        textStyle = androidx.compose.ui.text.TextStyle(fontSize = 10.sp, color = Color(0xFFE2E8F0)),
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        modifier = Modifier.weight(1f).height(30.dp).background(Color(0xFF0F172A), RoundedCornerShape(5.dp)).border(1.dp, Color(0xFF334155), RoundedCornerShape(5.dp)).padding(horizontal = 6.dp, vertical = 7.dp)
                    )
                    Text(",", fontSize = 10.sp, color = Color(0xFF64748B))
                    BasicTextField(
                        value = maxText,
                        onValueChange = { txt ->
                            maxText = txt.filter { it.isDigit() }.take(4)
                            maxText.toIntOrNull()?.let { v ->
                                val r = sanitizeChannelRange(minVal, v)
                                onValue(keys.minKey, r.first)
                                onValue(keys.maxKey, r.second)
                            }
                        },
                        singleLine = true,
                        textStyle = androidx.compose.ui.text.TextStyle(fontSize = 10.sp, color = Color(0xFFE2E8F0)),
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                        modifier = Modifier.weight(1f).height(30.dp).background(Color(0xFF0F172A), RoundedCornerShape(5.dp)).border(1.dp, Color(0xFF334155), RoundedCornerShape(5.dp)).padding(horizontal = 6.dp, vertical = 7.dp)
                    )
                }
            }

            @Composable
            fun SourcePickerDialog(channelIndex: Int, current: String, sources: List<String>, onPick: (String) -> Unit, onDismiss: () -> Unit) {
                val known = if (sources.isEmpty()) {
                    listOf("ch1", "ch2", "ch3", "ch4", "ch5", "ch6", "dial", "mode", "rec", "rth", "stop", "focus", "c1", "c2", "c3", "aircraft", "back", "btn", "up", "down", "left", "right", "shot", "c12", "dir", "lr", "none")
                } else {
                    sources + "none"
                }
                val groups = listOf(
                    "摇杆&旋钮" to listOf("ch1", "ch2", "ch3", "ch4", "ch5", "ch6", "dial"),
                    "开关/按键" to listOf("rec", "rth", "stop", "focus", "c1", "c2", "c3", "aircraft", "back", "btn"),
                    "功能键" to listOf("mode", "shot", "c12", "dir", "up", "down", "left", "right", "none")
                )
                AlertDialog(
                    onDismissRequest = onDismiss,
                    containerColor = Color(0xFF0F172A),
                    title = { Text("CH${channelIndex + 1} 控件选择", color = Color(0xFFE2E8F0), fontSize = 16.sp, fontWeight = FontWeight.Bold) },
                    text = {
                        Column(verticalArrangement = Arrangement.spacedBy(10.dp), modifier = Modifier.fillMaxWidth()) {
                            groups.forEach { (name, items) ->
                                Text(name, fontSize = 11.sp, fontWeight = FontWeight.Bold, color = Color(0xFF38BDF8))
                                items.filter { known.contains(it) }.chunked(3).forEach { rowItems ->
                                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
                                        rowItems.forEach { src ->
                                            WorkbenchButton(sourceDisplayLabel(src), active = src == current, modifier = Modifier.weight(1f)) { onPick(src) }
                                        }
                                        repeat(3 - rowItems.size) { Spacer(Modifier.weight(1f)) }
                                    }
                                }
                            }
                        }
                    },
                    confirmButton = { TextButton(onClick = onDismiss) { Text("关闭") } }
                )
            }

            val channelSources = channelMapToList(roMap)
            val channelLocks = channelLocksToList(roLocks)
            Surface(color = Color(0xFF0F172A), shape = RoundedCornerShape(10.dp), border = androidx.compose.foundation.BorderStroke(1.dp, Color(0xFF1E293B)), modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.padding(10.dp)) {
                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                        Column {
                            Text("通道设置", fontSize = 15.sp, fontWeight = FontWeight.Bold, color = Color(0xFF38BDF8))
                            Text("CH1-CH16 输出源 / 范围 / 反向", fontSize = 9.sp, color = Color(0xFF64748B))
                        }
                        Text(if (loaded) "● 已连接" else "○ 未连接", fontSize = 9.sp, color = if (loaded) Color(0xFF22C55E) else Color(0xFFF59E0B))
                    }
                    Spacer(Modifier.height(8.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
                        WorkbenchButton("默认配置") {
                            roPreset = "default"
                            roMap = DEFAULT_CHANNEL_MAP
                            roLocks = channelLocksToString(emptyList())
                            srcCfg = SRC_CFG_GROUPS.flatMap { it.second }.associate { it.key to it.def }
                            roMsg = "已恢复默认, 保存后生效"
                        }
                        WorkbenchButton("载入配置") { roMsg = "载入配置入口已预留" }
                        WorkbenchButton("配置另存") { roMsg = "配置另存入口已预留" }
                        WorkbenchButton("参数管理", advancedExpanded) { advancedExpanded = !advancedExpanded }
                        Spacer(Modifier.weight(1f))
                        WorkbenchButton("SBUS", rcOutMode == "sbus") { rcOutMode = "sbus" }
                        WorkbenchButton("CRSF", rcOutMode == "crsf") { rcOutMode = "crsf" }
                    }
                    Spacer(Modifier.height(8.dp))
                    Column(modifier = Modifier.fillMaxWidth().background(Color(0xFF111827), RoundedCornerShape(8.dp)).border(1.dp, Color(0xFF1E293B), RoundedCornerShape(8.dp)).padding(6.dp)) {
                        Row(modifier = Modifier.fillMaxWidth().padding(horizontal = 6.dp, vertical = 2.dp), verticalAlignment = Alignment.CenterVertically) {
                            Text("通道", fontSize = 9.sp, color = Color(0xFF64748B), modifier = Modifier.width(40.dp))
                            Text("控件", fontSize = 9.sp, color = Color(0xFF64748B), modifier = Modifier.width(96.dp))
                            Text("当前输出值", fontSize = 9.sp, color = Color(0xFF64748B), modifier = Modifier.weight(1f))
                            Text("反向", fontSize = 9.sp, color = Color(0xFF64748B), modifier = Modifier.width(48.dp))
                            Text("自锁", fontSize = 9.sp, color = Color(0xFF64748B), modifier = Modifier.width(48.dp))
                            Text("长按", fontSize = 9.sp, color = Color(0xFF64748B), modifier = Modifier.width(48.dp))
                            Text("范围", fontSize = 9.sp, color = Color(0xFF64748B), modifier = Modifier.width(128.dp))
                        }
                        channelSources.forEachIndexed { idx, source ->
                            val keys = sourceKeys(source)
                            val value = channelOutputValue(rcChs, idx)
                            val lockEnabled = sourceSupportsLock(source)
                            Row(
                                modifier = Modifier.fillMaxWidth().height(42.dp).background(if (idx % 2 == 0) Color(0xFF0F172A) else Color(0xFF111827), RoundedCornerShape(4.dp)).border(0.5.dp, Color(0xFF1E293B), RoundedCornerShape(4.dp)).padding(horizontal = 6.dp, vertical = 5.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Text("CH${idx + 1}", fontSize = 11.sp, fontWeight = FontWeight.Bold, color = Color(0xFFE2E8F0), modifier = Modifier.width(40.dp))
                                WorkbenchButton(sourceDisplayLabel(source), modifier = Modifier.width(96.dp)) { selectedSourceChannel = idx }
                                Spacer(Modifier.width(8.dp))
                                ChannelScale(value, modifier = Modifier.weight(1f))
                                Spacer(Modifier.width(8.dp))
                                Checkbox(
                                    checked = (srcCfg[keys.revKey] ?: 0) != 0,
                                    enabled = srcCfgLoaded && keys.revKey.isNotEmpty(),
                                    onCheckedChange = { checked ->
                                        if (keys.revKey.isNotEmpty()) srcCfg = srcCfg + (keys.revKey to if (checked) 1 else 0)
                                    },
                                    modifier = Modifier.size(40.dp)
                                )
                                Checkbox(
                                    checked = channelLocks.getOrElse(idx) { false },
                                    enabled = lockEnabled,
                                    onCheckedChange = { checked ->
                                        val next = channelLocks.toMutableList()
                                        next[idx] = checked
                                        roLocks = channelLocksToString(next)
                                    },
                                    modifier = Modifier.size(40.dp)
                                )
                                val lpKey = sourceLpKey(source)
                                Checkbox(
                                    checked = (srcCfg[lpKey] ?: 0) != 0,
                                    enabled = srcCfgLoaded && lpKey.isNotEmpty(),
                                    onCheckedChange = { checked ->
                                        if (lpKey.isNotEmpty()) srcCfg = srcCfg + (lpKey to if (checked) 1 else 0)
                                    },
                                    modifier = Modifier.size(40.dp)
                                )
                                RangeEditor(source, srcCfg, srcCfgLoaded) { k, v -> srcCfg = srcCfg + (k to v) }
                            }
                            if (idx != channelSources.lastIndex) Spacer(Modifier.height(3.dp))
                        }
                    }
                    if (advancedExpanded) {
                        Spacer(Modifier.height(10.dp))
                        Column(
                            modifier = Modifier
                                .fillMaxWidth()
                                .background(Color(0xFF111827), RoundedCornerShape(8.dp))
                                .border(1.dp, Color(0xFF1E293B), RoundedCornerShape(8.dp))
                                .padding(10.dp),
                            verticalArrangement = Arrangement.spacedBy(8.dp)
                        ) {
                            Text("高级参数管理", fontSize = 12.sp, fontWeight = FontWeight.Bold, color = Color(0xFF38BDF8))
                            Text("保留完整 src_cfg 调参项，用于 mode / shot / 方向键等多档位控件。", fontSize = 9.sp, color = Color(0xFF64748B))
                            if (srcCfgLoaded) {
                                SRC_CFG_GROUPS.forEach { (name, rows) ->
                                    SrcCfgGroup(name, rows, srcCfg) { key, value ->
                                        srcCfg = srcCfg + (key to value)
                                    }
                                }
                            } else {
                                Text("当前固件未上报 src_cfg_names，高级参数仅在支持固件上开放。", fontSize = 9.sp, color = Color(0xFFF59E0B))
                            }
                        }
                    }
                    Spacer(Modifier.height(10.dp))
                    Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                        Button(onClick = {
                            roMsg = ""
                            val scJson = SRC_CFG_GROUPS.flatMap { it.second }
                                .joinToString(",") { "\"${it.key}\":${srcCfg[it.key] ?: it.def}" }
                            val scPart = if (srcCfgLoaded) ""","src_cfg":{$scJson}""" else ""
                            val body = """{"mode":"$rcOutMode","baud":"$roBaud","map_preset":"$roPreset","map":"${channelMapToString(channelSources)}","lock":"${channelLocksToString(channelLocks)}","sbus_std":$roSbusStd$scPart}"""
                            apiPost("/api/rc/output", body) { ok ->
                                roMsg = if (ok) "已保存, V3s 将自动应用" else "保存失败, 请检查连接"
                            }
                        }, modifier = Modifier.height(34.dp), colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF2563EB)), contentPadding = PaddingValues(horizontal = 14.dp, vertical = 0.dp)) { Text("保存并应用", fontSize = 11.sp) }
                        Button(onClick = { roReload++ }, modifier = Modifier.height(34.dp), colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF334155)), contentPadding = PaddingValues(horizontal = 14.dp, vertical = 0.dp)) { Text("刷新", fontSize = 11.sp) }
                        if (!srcCfgLoaded) Text("固件未上报 src_cfg, 范围/反向保存将跳过", fontSize = 8.sp, color = Color(0xFFF59E0B))
                        if (roMsg.isNotEmpty()) Text(roMsg, fontSize = 9.sp, color = Color(0xFF94A3B8), modifier = Modifier.weight(1f))
                    }
                }
            }
            selectedSourceChannel?.let { idx ->
                SourcePickerDialog(idx, channelSources[idx], roSources, onPick = { src ->
                    val next = channelSources.toMutableList()
                    next[idx] = src
                    roMap = channelMapToString(next)
                    if (!sourceSupportsLock(src)) {
                        val nextLocks = channelLocks.toMutableList()
                        nextLocks[idx] = false
                        roLocks = channelLocksToString(nextLocks)
                    }
                    roPreset = "custom"
                    selectedSourceChannel = null
                }, onDismiss = { selectedSourceChannel = null })
            }
        }

        Column(modifier = Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp)) {
            Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Column {
                    Text("RC 遥控", fontSize = 18.sp, fontWeight = FontWeight.Bold, color = Color(0xFF38BDF8))
                    Text(
                        rcTopStatusText(
                            rcConnected,
                            rcInputMode,
                            rcType,
                            serviceRcSourceStats.geteventHz,
                            serviceRcSourceStats.p40007Hz,
                            v3sRcMsgHz
                        ),
                        fontSize = 11.sp, color = if (rcConnected) Color(0xFF22C55E) else Color(0xFF64748B)
                    )
                }
                ModeSwitch(rcMode)
            }
            Spacer(Modifier.height(8.dp))

            Text("SBUS CH1-CH16", fontSize = 10.sp, fontWeight = FontWeight.Bold, color = Color(0xFFE2E8F0))
            Spacer(Modifier.height(5.dp))
            SbusChannelGrid()

            Spacer(Modifier.height(6.dp))
            Text("按键 / 拨轮", fontSize = 10.sp, fontWeight = FontWeight.Bold, color = Color(0xFFE2E8F0))
            Spacer(Modifier.height(5.dp))
            ButtonStatusGrid()

            Spacer(Modifier.height(6.dp))
            Text("方向键", fontSize = 10.sp, fontWeight = FontWeight.Bold, color = Color(0xFFE2E8F0))
            Spacer(Modifier.height(5.dp))
            DpadStatus()

            Spacer(Modifier.height(8.dp))
            HorizontalDivider(color = Color(0xFF1E293B))
            Spacer(Modifier.height(8.dp))
            RemoteChannelConfig()
        }
    }

    // ═══════════════════════════════════════════════
    // UI 布局
    // ═══════════════════════════════════════════════

    MaterialTheme(colorScheme = darkColorScheme(
        background = Color(0xFF0F172A), surface = Color(0xFF1E293B), primary = Color(0xFF38BDF8),
        onBackground = Color(0xFFE2E8F0), onSurface = Color(0xFFE2E8F0)
    )) {
        Column(modifier = Modifier.fillMaxSize().background(Color(0xFF0F172A))) {

            // ═══ TopBar — 单行紧凑 ═══
            Surface(modifier = Modifier.fillMaxWidth(), color = Color(0xFF0F172A), shadowElevation = 4.dp) {
                Row(modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 5.dp).height(32.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    // 左侧: USB● VPN● + 状态
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Surface(shape = CircleShape, color = if (usbFound) Color(0xFF22C55E) else Color(0xFFEF4444), modifier = Modifier.size(6.dp)) {}
                        Spacer(Modifier.width(3.dp))
                        Surface(shape = CircleShape, color = if (vpnRunning) Color(0xFF22C55E) else Color(0xFFEF4444), modifier = Modifier.size(6.dp)) {}
                        Spacer(Modifier.width(6.dp))
                        if (TunNatVpnService.isReconnectingState.value) {
                            // 最高优先：正在重连
                            Text("USB 重连...", fontSize = 11.sp, color = Color(0xFFF59E0B), fontWeight = FontWeight.Medium)
                        } else if (vpnRunning && hbCount > 0) {
                            Text("${hbBw} Mbps", fontSize = 12.sp, fontWeight = FontWeight.Medium, color = Color(0xFF38BDF8))
                            Spacer(Modifier.width(10.dp))
                            Text("Tx${fmtSize(hbTx)} Rx${fmtSize(hbRx)}", fontSize = 10.sp, color = Color(0xFF64748B))
                        } else if (!vpnRunning) {
                            val st = when (connectionState) {
                                "scanning" -> if (usbPollCount > 0) "搜索中 (${usbPollCount}s)" else "搜索中..."
                                "timeout" -> "未找到设备"
                                "found" -> "已发现，点击连接"
                                else -> "插入 USB 线"
                            }
                            Text(st, fontSize = 11.sp, color = Color(0xFF64748B))
                        } else {
                            Text("链路建立中...", fontSize = 11.sp, color = Color(0xFFF59E0B))
                        }
                    }
                    // 右侧: 连/断按钮
                    Button(onClick = onVpnTap, enabled = usbFound,
                        modifier = Modifier.height(24.dp),
                        contentPadding = PaddingValues(horizontal = 10.dp, vertical = 0.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = if (vpnRunning) Color(0xFFDC2626) else Color(0xFF2563EB))
                    ) { Text(if (vpnRunning) "断开" else "连接", fontSize = 10.sp) }
                }
            }

            // ── 网段变更提示 ──
            if (needVpnReconnect) {
                Row(modifier = Modifier.fillMaxWidth().background(Color(0x33F59E0B)).padding(horizontal = 14.dp, vertical = 4.dp),
                    horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically
                ) {
                    Text("网段已变更: $savedLanSubnet/$savedLanPrefix", fontSize = 10.sp, color = Color(0xFFFBBF24))
                    Button(onClick = {
                        needVpnReconnect = false
                        if (vpnRunning) onVpnTap()
                        onReconnect?.invoke()
                    }, modifier = Modifier.height(22.dp), contentPadding = PaddingValues(horizontal = 8.dp, vertical = 0.dp),
                        colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFF59E0B))
                    ) { Text("重连", fontSize = 10.sp, color = Color.Black) }
                }
            }

            HorizontalDivider(color = Color(0xFF1E293B))

            // ═══ 主体: 导航栏 + 内容区 ═══
            Row(modifier = Modifier.weight(1f)) {

                // ── NavRail ──
                Surface(modifier = Modifier.width(48.dp).fillMaxHeight(), color = Color(0xFF111827)) {
                    Column(modifier = Modifier.fillMaxHeight(), horizontalAlignment = Alignment.CenterHorizontally) {
                        Spacer(Modifier.height(12.dp))
                        IconButton(onClick = { selectedTab = Tab.VIDEO }, modifier = Modifier.size(40.dp)) {
                            Icon(Icons.Filled.PlayArrow, "视频",
                                tint = if (selectedTab == Tab.VIDEO) Color(0xFF38BDF8) else Color(0xFF475569),
                                modifier = Modifier.size(22.dp))
                        }
                        Text("视频", fontSize = 9.sp, color = if (selectedTab == Tab.VIDEO) Color(0xFF38BDF8) else Color(0xFF475569))
                        Spacer(Modifier.height(12.dp))
                        IconButton(onClick = { selectedTab = Tab.REMOTE }, modifier = Modifier.size(40.dp)) {
                            Icon(Icons.Filled.SportsEsports, "遥控",
                                tint = if (selectedTab == Tab.REMOTE) Color(0xFF38BDF8) else Color(0xFF475569),
                                modifier = Modifier.size(22.dp))
                        }
                        Text("遥控", fontSize = 9.sp, color = if (selectedTab == Tab.REMOTE) Color(0xFF38BDF8) else Color(0xFF475569))
                        Spacer(Modifier.height(12.dp))
                        // 接收机 (ELRS Lua) 仅在 CRSF 协议 (ELRS 模式) 时显示
                        if (rcOutMode == "crsf") {
                            IconButton(onClick = { selectedTab = Tab.RECEIVER }, modifier = Modifier.size(40.dp)) {
                                Icon(Icons.Filled.Radio, "接收机",
                                    tint = if (selectedTab == Tab.RECEIVER) Color(0xFF38BDF8) else Color(0xFF475569),
                                    modifier = Modifier.size(22.dp))
                            }
                            Text("接收机", fontSize = 9.sp, color = if (selectedTab == Tab.RECEIVER) Color(0xFF38BDF8) else Color(0xFF475569))
                            Spacer(Modifier.height(12.dp))
                        }
                        IconButton(onClick = { selectedTab = Tab.CONFIG }, modifier = Modifier.size(40.dp)) {
                            Icon(Icons.Filled.Settings, "配置",
                                tint = if (selectedTab == Tab.CONFIG) Color(0xFF38BDF8) else Color(0xFF475569),
                                modifier = Modifier.size(22.dp))
                        }
                        Text("配置", fontSize = 9.sp, color = if (selectedTab == Tab.CONFIG) Color(0xFF38BDF8) else Color(0xFF475569))
                        Spacer(Modifier.weight(1f))
                        Text("v${BuildConfig.VERSION_NAME}", fontSize = 9.sp, color = Color(0xFF475569))
                        if (v3sVersion.isNotEmpty()) {
                            Text("F$v3sVersion", fontSize = 9.sp, color = Color(0xFF475569))
                        }
                        Spacer(Modifier.height(8.dp))
                    }
                }

                VerticalDivider(color = Color(0xFF1E293B))

                // ── 内容区：视频始终保留，配置页覆盖 ──
                Box(modifier = Modifier.weight(1f).fillMaxHeight()) {
                    // 视频区 — 始终在 composition 中
                    var showUrlBar by remember { mutableStateOf(true) }  // 默认显示，点视频切换
                    Box(modifier = Modifier.fillMaxSize()) {
                        // 视频画面 — 点击切换 RTSP 栏
                        Surface(modifier = Modifier.fillMaxSize().padding(4.dp).clickable { showUrlBar = !showUrlBar },
                            color = Color(0xFF020617), shape = RoundedCornerShape(8.dp)
                        ) {
                            Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                                // QGC_SOFTWARE 引擎用 GLSurfaceView 低延迟渲染（绕开 SurfaceView 队列），
                                // 其他引擎保持 SurfaceView。
                                AndroidView(
                                    factory = { vctx ->
                                        if (playbackEngine == RtspPlaybackEngine.QGC_SOFTWARE) {
                                            val gl = com.tunnathub.app.video.GlLowLatencySurface(vctx)
                                            glSurfaceRef = gl
                                            gl.view
                                        } else {
                                            SurfaceView(vctx).apply {
                                                surfaceViewRef = this
                                                // Surface 生命周期: 就绪才允许播放, 销毁标记失效。
                                                // 修复回前台后 Surface 未重建完成就播放 → render 每帧失败画面卡死。
                                                holder.addCallback(object : android.view.SurfaceHolder.Callback {
                                                    override fun surfaceCreated(holder: android.view.SurfaceHolder) {
                                                        surfaceReady = true
                                                        // Surface 就绪了, 若之前有挂起的播放请求 (切后台回前台/自动播放), 立即启动
                                                        if (pendingPlayAfterSurface && !isPlaying && vpnRunning) {
                                                            pendingPlayAfterSurface = false
                                                            startPlaybackFn()
                                                        }
                                                    }
                                                    override fun surfaceChanged(holder: android.view.SurfaceHolder, format: Int, width: Int, height: Int) {}
                                                    override fun surfaceDestroyed(holder: android.view.SurfaceHolder) {
                                                        surfaceReady = false
                                                    }
                                                })
                                            }
                                        }
                                    },
                                    modifier = Modifier.fillMaxWidth(0.94f).aspectRatio(16f / 9f),
                                    update = { sv -> sv.layoutParams = FrameLayout.LayoutParams(FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT).apply { gravity = android.view.Gravity.CENTER } })
                                if (!isPlaying) {
                                    Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                        Text(if (!usbFound) "等待 USB 连接..." else if (!vpnRunning) "启动 VPN 隧道" else "输入 RTSP 地址并点击播放", fontSize = 14.sp, color = Color(0xFF475569))
                                    }
                                }
                            }
                        }

                        // RTSP 信息栏 (顶部，非全屏时显示，点击视频画面切换) — 仅在视频 Tab 显示
                        if (selectedTab == Tab.VIDEO && showUrlBar) {
                            Surface(modifier = Modifier.align(Alignment.TopCenter).fillMaxWidth().padding(8.dp),
                                color = Color(0xDD0F172A), shape = RoundedCornerShape(8.dp)
                            ) {
                                Column(modifier = Modifier.padding(horizontal = 12.dp, vertical = 6.dp)) {
                                    Row(modifier = Modifier.fillMaxWidth(),
                                        horizontalArrangement = Arrangement.SpaceBetween,
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Column(modifier = Modifier.weight(1f)) {
                                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                                                if (statusText.isNotEmpty()) Text(statusText, fontSize = 10.sp, color = if (isPlaying) Color(0xFF22C55E) else Color(0xFF94A3B8), maxLines = 1)
                                                if (resolutionText.isNotEmpty()) Text(resolutionText, fontSize = 10.sp, color = Color(0xFF64748B))
                                            }
                                            Spacer(Modifier.height(4.dp))
                                            Box(modifier = Modifier.fillMaxWidth().height(34.dp).background(Color(0xFF020617), RoundedCornerShape(6.dp)).border(1.dp, Color(0xFF334155), RoundedCornerShape(6.dp)).padding(horizontal = 10.dp), contentAlignment = Alignment.CenterStart) {
                                                BasicTextField(value = rtspUrl, onValueChange = { rtspUrl = it }, singleLine = true,
                                                    textStyle = androidx.compose.ui.text.TextStyle(fontSize = 13.sp, color = Color(0xFFE2E8F0)),
                                                    cursorBrush = androidx.compose.ui.graphics.SolidColor(Color(0xFF38BDF8)),
                                                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri, imeAction = ImeAction.Done), modifier = Modifier.fillMaxWidth())
                                            }
                                        }
                                        Spacer(Modifier.width(8.dp))
                                        Button(onClick = { togglePlay() }, modifier = Modifier.height(34.dp),
                                            colors = ButtonDefaults.buttonColors(containerColor = if (isPlaying) Color(0xFFDC2626) else Color(0xFF16A34A))
                                        ) { Text(if (isPlaying) "■" else "▶", fontSize = 12.sp) }
                                    }
                                }
                            }
                        }
                    }

                    if (selectedTab == Tab.REMOTE) {
                        Surface(modifier = Modifier.fillMaxSize(), color = Color(0xFF0F172A)) {
                            RcPanelContent()
                        }
                    }

                    // 接收机页: 内嵌 ELRS Lua 参数界面 (当前 mock 假数据)
                    if (selectedTab == Tab.RECEIVER) {
                        Surface(modifier = Modifier.fillMaxSize(), color = Color(0xFF0F172A)) {
                            LuaParamEmbed()
                        }
                    }

                    // 配置页覆盖层
                    if (selectedTab == Tab.CONFIG) {
                        val scrollState = rememberScrollState()
                        Surface(modifier = Modifier.fillMaxSize(), color = Color(0xFF0F172A)) {
                            Column(modifier = Modifier.fillMaxSize().verticalScroll(scrollState).padding(16.dp)) {
                                @Composable fun SectionHdr(t: String) { Text(t, fontSize = 13.sp, fontWeight = FontWeight.Bold, color = Color(0xFF38BDF8), modifier = Modifier.padding(bottom = 6.dp)) }

                                // ELRS 参数配置入口 (Lua 脚本驱动)
                                SectionHdr("ELRS 参数")
                                Text("连接 V3s crsf-bridge, 用 Lua 脚本配置 ELRS 模块射频参数", fontSize = 9.sp, color = Color(0xFF475569))
                                Spacer(Modifier.height(6.dp))
                                Button(
                                    onClick = {
                                        ctx.startActivity(
                                            android.content.Intent(ctx, com.tunnathub.app.crsf.LuaParamActivity::class.java)
                                                .putExtra("host", "192.168.144.66")
                                        )
                                    },
                                    modifier = Modifier.fillMaxWidth().height(40.dp),
                                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF0EA5E9))
                                ) { Text("打开 ELRS 参数配置", fontSize = 13.sp) }
                                Spacer(Modifier.height(12.dp))

                                // ── LAN 身份说明 (网段配置/端口转发已移除: 手机=局域网真 IP, 零配置直达) ──
                                Spacer(Modifier.height(16.dp)); HorizontalDivider(color = Color(0xFF1E293B)); Spacer(Modifier.height(12.dp))
                                SectionHdr("局域网直连 (LAN 身份)")
                                Text("手机 = $savedLanSubnet 网段的 .11 (如 192.168.144.11),\nV3s = .66。局域网设备直接访问手机任意端口,\n无需端口转发 / 网段配置。", fontSize = 10.sp, color = Color(0xFF64748B), lineHeight = 15.sp)

                                // ── RC 输入链路: 当前安卓融合 vs 旧链路 V3s rcmsg ──
                                Spacer(Modifier.height(16.dp)); HorizontalDivider(color = Color(0xFF1E293B)); Spacer(Modifier.height(12.dp))
                                SectionHdr("RC 输入链路")
                                Text(
                                    if (rcInputMode == RcInputMode.V3S_RCMSG)
                                        "串口 → V3s → rcmsg → App，不启动 ADB/getevent/40007 采集。"
                                    else
                                        "Android 本地融合 getevent + 40007，CH1-6 即时，本地发布给 V3s。",
                                    fontSize = 9.sp,
                                    color = Color(0xFF64748B)
                                )
                                Spacer(Modifier.height(8.dp))
                                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                                    listOf(RcInputMode.ANDROID_FUSION, RcInputMode.V3S_RCMSG).forEach { mode ->
                                        Surface(
                                            color = if (rcInputMode == mode) Color(0xFF0EA5E9) else Color(0xFF1E293B),
                                            shape = RoundedCornerShape(6.dp),
                                            onClick = {
                                                rcInputMode = mode
                                                prefs.edit().putString(RcInputMode.PREF_KEY, mode.prefValue).apply()
                                                TunNatVpnService.requestRcFusionRestart()
                                                if (mode == RcInputMode.ANDROID_FUSION) {
                                                    (ctx as? MainActivity)?.ensureShizukuPermission()
                                                }
                                                AppLog.i("RcInput", "输入链路切换: ${mode.prefValue}")
                                            }
                                        ) {
                                            Text(
                                                mode.label,
                                                fontSize = 11.sp,
                                                fontWeight = FontWeight.Bold,
                                                color = if (rcInputMode == mode) Color.Black else Color(0xFF64748B),
                                                modifier = Modifier.padding(horizontal = 14.dp, vertical = 6.dp)
                                            )
                                        }
                                    }
                                }

                                // ── RC 输出 (SBUS/CRSF @UART0) ──
                                Spacer(Modifier.height(16.dp)); HorizontalDivider(color = Color(0xFF1E293B)); Spacer(Modifier.height(12.dp))
                                SectionHdr("RC 输出 (UART0)")
                                Text("SBUS 100k 8E2 / CRSF 420k 8N1, 可自定义通道映射 (参考 EdgeTX)", fontSize = 9.sp, color = Color(0xFF64748B))
                                Spacer(Modifier.height(8.dp))

                                var roBaud by remember { mutableStateOf("auto") }
                                var roPreset by remember { mutableStateOf("default") }
                                var roMap by remember { mutableStateOf("") }
                                var roSbusStd by remember { mutableStateOf(true) }
                                var roMsg by remember { mutableStateOf("") }
                                var roReload by remember { mutableStateOf(0) }   // 每次进入 +1 强制重载

                                // 加载当前配置: 进入配置页时强制从 V3s 读取 (含已保存的 crsf/sbus 模式)
                                LaunchedEffect(vpnRunning, roReload) {
                                    if (!vpnRunning) return@LaunchedEffect
                                    roMsg = "读取中..."
                                    // H-3: 网络请求放 IO 线程, 避免阻塞主线程 (ANR 风险)
                                    val result = kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
                                        try {
                                            val text = java.net.URL("http://192.168.144.66:8080/api/rc/output").openConnection()
                                                .apply { connectTimeout = 3000; readTimeout = 3000 }
                                                .getInputStream().bufferedReader().readText()
                                            Pair(text, "")  // (内容, 错误)
                                        } catch (e: Exception) {
                                            Pair("", "读取失败, 点刷新重试")
                                        }
                                    }
                                    val text = result.first
                                    if (text.isNotEmpty()) {
                                        rcOutMode = jsonString(text, "mode") ?: "sbus"
                                        roBaud = jsonString(text, "baud") ?: "auto"
                                        roPreset = jsonString(text, "map_preset") ?: "default"
                                        roMap = jsonString(text, "map") ?: ""
                                        // sbus_std 是布尔(false 无引号), jsonString 正则只匹配带引号字符串 → 会误读。
                                        // 用布尔正则: 匹配 true/false 字面量
                                        roSbusStd = when {
                                            Regex("\"sbus_std\"\\s*:\\s*false").containsMatchIn(text) -> false
                                            else -> true
                                        }
                                        roMsg = if (roReload > 0) "已读取配置" else ""
                                    } else {
                                        roMsg = result.second
                                    }
                                }

                                // 模式
                                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                                    Text("模式", fontSize = 11.sp, color = Color(0xFF94A3B8), modifier = Modifier.width(44.dp))
                                    listOf("sbus" to "SBUS", "crsf" to "CRSF").forEach { (v, label) ->
                                        Surface(color = if (rcOutMode == v) Color(0xFF0EA5E9) else Color(0xFF1E293B), shape = RoundedCornerShape(6.dp),
                                            onClick = { rcOutMode = v }) {
                                            Text(label, fontSize = 11.sp, fontWeight = FontWeight.Bold, color = if (rcOutMode == v) Color.Black else Color(0xFF64748B), modifier = Modifier.padding(horizontal = 14.dp, vertical = 6.dp))
                                        }
                                    }
                                    Spacer(Modifier.weight(1f))
                                    Text(if (rcOutMode == "crsf") "含回传" else "单向", fontSize = 9.sp, color = if (rcOutMode == "crsf") Color(0xFF22C55E) else Color(0xFF64748B))
                                }

                                // 标准 SBUS 开关 (仅 SBUS 模式)
                                if (rcOutMode == "sbus") {
                                    Spacer(Modifier.height(8.dp))
                                    Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                        Text("标准 SBUS", fontSize = 11.sp, color = Color(0xFF94A3B8), modifier = Modifier.width(66.dp))
                                        Surface(color = if (roSbusStd) Color(0xFF0EA5E9) else Color(0xFF1E293B), shape = RoundedCornerShape(6.dp),
                                            onClick = { roSbusStd = true; roBaud = "auto" }) {
                                            Text("100k 8E2", fontSize = 10.sp, fontWeight = FontWeight.Bold, color = if (roSbusStd) Color.Black else Color(0xFF64748B), modifier = Modifier.padding(horizontal = 10.dp, vertical = 5.dp))
                                        }
                                        Surface(color = if (!roSbusStd) Color(0xFF0EA5E9) else Color(0xFF1E293B), shape = RoundedCornerShape(6.dp),
                                            onClick = { roSbusStd = false; roBaud = "auto" }) {
                                            Text("115200 8N1", fontSize = 10.sp, fontWeight = FontWeight.Bold, color = if (!roSbusStd) Color.Black else Color(0xFF64748B), modifier = Modifier.padding(horizontal = 10.dp, vertical = 5.dp))
                                        }
                                        Text(if (roSbusStd) "标准" else "兼容", fontSize = 9.sp, color = if (roSbusStd) Color(0xFF22C55E) else Color(0xFFF59E0B))
                                    }
                                }

                                // 波特率
                                Spacer(Modifier.height(8.dp))
                                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                                    Text("波特率", fontSize = 11.sp, color = Color(0xFF94A3B8), modifier = Modifier.width(44.dp))
                                    Surface(color = if (roBaud == "auto") Color(0xFF0EA5E9) else Color(0xFF1E293B), shape = RoundedCornerShape(6.dp),
                                        onClick = { roBaud = "auto" }) {
                                        Text("自动", fontSize = 10.sp, color = if (roBaud == "auto") Color.Black else Color(0xFF64748B), modifier = Modifier.padding(horizontal = 12.dp, vertical = 5.dp))
                                    }
                                    Surface(color = if (roBaud != "auto") Color(0xFF0EA5E9) else Color(0xFF1E293B), shape = RoundedCornerShape(6.dp),
                                        onClick = { roBaud = if (rcOutMode == "crsf") "400000" else if (roSbusStd) "100000" else "115200" }) {
                                        Text("手动", fontSize = 10.sp, color = if (roBaud != "auto") Color.Black else Color(0xFF64748B), modifier = Modifier.padding(horizontal = 12.dp, vertical = 5.dp))
                                    }
                                    if (roBaud != "auto") {
                                        Box(modifier = Modifier.weight(1f).height(28.dp).background(Color(0xFF0F172A), RoundedCornerShape(6.dp)).border(1.dp, Color(0xFF334155), RoundedCornerShape(6.dp)).padding(horizontal = 8.dp), contentAlignment = Alignment.CenterStart) {
                                            BasicTextField(value = roBaud, onValueChange = { roBaud = it }, singleLine = true,
                                                textStyle = androidx.compose.ui.text.TextStyle(fontSize = 11.sp, color = Color(0xFFE2E8F0)),
                                                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), modifier = Modifier.fillMaxWidth())
                                        }
                                    } else {
                                        // auto: 实际波特率由固件按 sbus_std 决定 (std→100k, 非std→115200; CRSF→420k)
                                        Text(if (rcOutMode == "crsf") "→ 400000" else if (roSbusStd) "→ 100000" else "→ 115200",
                                            fontSize = 10.sp, color = Color(0xFF22C55E))
                                    }
                                }

                                // 通道映射已移到左侧栏"遥控"页的通道设置工作台

                                // 保存 + 刷新
                                Spacer(Modifier.height(10.dp))
                                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp), verticalAlignment = Alignment.CenterVertically) {
                                    Button(onClick = {
                                        roMsg = ""
                                        val body = """{"mode":"$rcOutMode","baud":"$roBaud","map_preset":"$roPreset","map":"$roMap","sbus_std":$roSbusStd}"""
                                        apiPost("/api/rc/output", body) { ok ->
                                            roMsg = if (ok) "已保存, V3s 将自动应用" else "保存失败, 请检查连接"
                                        }
                                    }, modifier = Modifier.height(32.dp), colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF2563EB)), contentPadding = PaddingValues(horizontal = 12.dp, vertical = 0.dp)) { Text("保存并应用", fontSize = 11.sp) }
                                    Button(onClick = { roReload++ },
                                        modifier = Modifier.height(32.dp), colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF334155)), contentPadding = PaddingValues(horizontal = 12.dp, vertical = 0.dp)) { Text("刷新", fontSize = 11.sp) }
                                    if (roMsg.isNotEmpty()) Text(roMsg, fontSize = 9.sp, color = Color(0xFF94A3B8), modifier = Modifier.weight(1f))
                                }

                                // 回传数据 (CRSF 模式)
                                if (rcOutMode == "crsf") {
                                    Spacer(Modifier.height(10.dp))
                                    Text("CRSF 回传数据", fontSize = 10.sp, fontWeight = FontWeight.Bold, color = Color(0xFFE2E8F0))
                                    var tlText by remember { mutableStateOf("等待回传...") }
                                    LaunchedEffect(rcOutMode, roReload) {
                                        if (rcOutMode != "crsf") return@LaunchedEffect
                                        while (true) {
                                            // H-4: 网络请求放 IO 线程, 避免阻塞主线程
                                            val res = kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
                                                try {
                                                    java.net.URL("http://192.168.144.66:8080/api/rc/telemetry").openConnection()
                                                        .apply { connectTimeout = 1500; readTimeout = 1500 }
                                                        .getInputStream().bufferedReader().readText()
                                                } catch (e: kotlinx.coroutines.CancellationException) {
                                                    throw e
                                                } catch (_: Exception) { "" }
                                            }
                                            if (res.isNotEmpty()) {
                                                val lat = jsonString(res, "lat") ?: "-"
                                                val rem = jsonString(res, "remaining_pct") ?: "-"
                                                val upQ = jsonString(res, "up_quality") ?: "-"
                                                val dnQ = jsonString(res, "dn_quality") ?: "-"
                                                tlText = "链路 上行${upQ}% 下行${dnQ}% · 电量 ${rem}% · GPS lat=$lat"
                                            } else {
                                                tlText = "回传不可用"
                                            }
                                            kotlinx.coroutines.delay(2000)
                                        }
                                    }
                                    Text(tlText, fontSize = 9.sp, color = Color(0xFF64748B), lineHeight = 13.sp)
                                }

                                // ── 播放引擎 + 解码器 (组合式下拉) ──
                                Spacer(Modifier.height(16.dp)); HorizontalDivider(color = Color(0xFF1E293B)); Spacer(Modifier.height(12.dp))
                                SectionHdr("播放引擎 / 解码器")
                                var selectedCodec by remember { mutableStateOf(LowLatencyRtspPlayer.getForcedCodec()) }
                                var codecList by remember { mutableStateOf(listOf("auto")) }
                                var comboDropdown by remember { mutableStateOf(false) }
                                // H-5: JNI 原生调用放 IO 线程, 避免阻塞主线程
                                LaunchedEffect(Unit) {
                                    val decoders = kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
                                        try { LowLatencyRtspPlayer.listAvailableDecoders() } catch (_: Exception) { emptyList() }
                                    }
                                    codecList = listOf("auto") + decoders
                                }
                                // 组合选项: 非 UDP_SELF 引擎单个选项(自动解码); UDP_SELF 每解码器一个选项
                                val comboLabel: String = if (playbackEngine == RtspPlaybackEngine.UDP_SELF) {
                                    "${playbackEngine.label()}:${selectedCodec.let { if (it == "auto") "自动" else if (it.contains("low_latency")) it.replace("c2.qti.avc.decoder.", "") + " ⚡" else it }}"
                                } else playbackEngine.label()
                                Box(modifier = Modifier.fillMaxWidth()) {
                                    Row(modifier = Modifier.fillMaxWidth().height(32.dp).background(Color(0xFF0F172A), RoundedCornerShape(6.dp)).border(1.dp, Color(0xFF334155), RoundedCornerShape(6.dp)).clickable { comboDropdown = !comboDropdown }.padding(horizontal = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                                        Text(comboLabel, fontSize = 10.sp, color = if (playbackEngine == RtspPlaybackEngine.GST_QGC) Color(0xFF22C55E) else Color(0xFFF59E0B), maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                                        Text(if (comboDropdown) "▲" else "▼", fontSize = 9.sp, color = Color(0xFF64748B))
                                    }
                                    DropdownMenu(expanded = comboDropdown, onDismissRequest = { comboDropdown = false }, modifier = Modifier.background(Color(0xFF1E293B))) {
                                        RtspPlaybackEngine.values().forEach { engine ->
                                            if (engine == RtspPlaybackEngine.UDP_SELF) {
                                                codecList.forEach { c ->
                                                    val cLabel = c.let { if (it == "auto") "自动" else if (it.contains("low_latency")) it.replace("c2.qti.avc.decoder.", "") + " ⚡" else it }
                                                    DropdownMenuItem(text = { Text("${engine.label()}: $cLabel", fontSize = 10.sp, color = Color(0xFFE2E8F0)) }, onClick = {
                                                        playbackEngine = engine
                                                        selectedCodec = c
                                                        comboDropdown = false
                                                        LowLatencyRtspPlayer.setForcedCodec(c)
                                                        prefs.edit().putString("playback_engine", engine.prefValue()).putString("forced_codec", c).apply()
                                                        AppLog.i("Player", "组合选择: ${engine.prefValue()} codec=$c")
                                                    }, modifier = Modifier.background(if (engine == playbackEngine && c == selectedCodec) Color(0xFF334155) else Color(0xFF1E293B)))
                                                }
                                            } else {
                                                DropdownMenuItem(text = { Text(engine.label(), fontSize = 10.sp, color = Color(0xFFE2E8F0)) }, onClick = {
                                                    playbackEngine = engine
                                                    selectedCodec = "auto"
                                                    comboDropdown = false
                                                    prefs.edit().putString("playback_engine", engine.prefValue()).apply()
                                                    AppLog.i("Player", "播放引擎切换: ${engine.prefValue()}")
                                                }, modifier = Modifier.background(if (engine == playbackEngine) Color(0xFF334155) else Color(0xFF1E293B)))
                                            }
                                        }
                                    }
                                }
                                Text(when (playbackEngine) {
                                    RtspPlaybackEngine.MEDIA3_UDP -> "Media3 默认 UDP 优先，用于验证摄像头/RTP UDP 是否可通。"
                                    RtspPlaybackEngine.QGC_SOFTWARE -> "QGC风格对照路径：自建UDP低缓冲 + Android软件H264解码。"
                                    RtspPlaybackEngine.GST_QGC -> "GStreamer引擎：rtspsrc+decodebin3+GL sink，完全参考 QGC 逻辑。"
                                    RtspPlaybackEngine.UDP_SELF -> "自建UDP低延迟硬解，下拉中可指定 H264 解码器。"
                                }, fontSize = 9.sp, color = Color(0xFF64748B), modifier = Modifier.padding(top = 3.dp))
                                Spacer(Modifier.height(6.dp))
                                Button(onClick = { doRunCodecBenchmark() }, enabled = !codecBenchmarkRunning && vpnRunning,
                                    modifier = Modifier.fillMaxWidth().height(30.dp),
                                    contentPadding = PaddingValues(horizontal = 8.dp, vertical = 0.dp),
                                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF0F766E))) {
                                    Text(if (codecBenchmarkRunning) "测试中..." else "自动测试 H264 解码器 1min", fontSize = 10.sp)
                                }
                                if (codecBenchmarkText.isNotEmpty()) {
                                    Text(codecBenchmarkText, fontSize = 9.sp, color = Color(0xFF38BDF8), lineHeight = 13.sp, modifier = Modifier.padding(top = 4.dp))
                                }

                                Spacer(Modifier.height(16.dp)); HorizontalDivider(color = Color(0xFF1E293B)); Spacer(Modifier.height(12.dp))
                                SectionHdr("诊断")
                                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                                    Text("隧道延迟", fontSize = 12.sp, color = Color(0xFF94A3B8))
                                    Button(onClick = {
                                        if (!testing && vpnRunning) {
                                            testing = true; latencyText = "测试中..."
                                            // M5: 协程替代裸 Thread, socket 用 use 保证关闭, state 切主线程写
                                            kotlinx.coroutines.CoroutineScope(kotlinx.coroutines.Dispatchers.IO).launch {
                                                val rtts = mutableListOf<Double>(); var drops = 0
                                                try {
                                                    for (i in 0 until 10) {
                                                        try {
                                                            val t0 = System.nanoTime()
                                                            java.net.Socket().use { s ->
                                                                s.connect(java.net.InetSocketAddress("192.168.144.66", 9999), 3000)
                                                                rtts.add((System.nanoTime() - t0) / 1_000_000.0)
                                                            }
                                                        } catch (_: Exception) { drops++ }
                                                    }
                                                    val result = if (rtts.isNotEmpty()) {
                                                        rtts.sort()
                                                        "%.1f/%.1f/%.1f ms (丢$drops)".format(rtts.average(), rtts[rtts.size / 2], rtts[(rtts.size * 0.95).toInt()])
                                                    } else "全部丢包 ($drops/10)"
                                                    withContext(kotlinx.coroutines.Dispatchers.Main) { latencyText = result }
                                                } catch (e: kotlinx.coroutines.CancellationException) {
                                                    throw e
                                                } catch (_: Exception) {
                                                    withContext(kotlinx.coroutines.Dispatchers.Main) { latencyText = "失败" }
                                                }
                                                withContext(kotlinx.coroutines.Dispatchers.Main) { testing = false }
                                            }
                                        }
                                    }, enabled = vpnRunning && !testing, modifier = Modifier.height(28.dp), contentPadding = PaddingValues(horizontal = 8.dp, vertical = 0.dp), colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF334155))) { Text(if (testing) "⏳" else "⏱", fontSize = 11.sp) }
                                }
                                if (latencyText.isNotEmpty()) Text(latencyText, fontSize = 10.sp, color = Color(0xFF38BDF8), modifier = Modifier.padding(top = 2.dp))

                                Spacer(Modifier.height(8.dp))
                                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                                    Text("RTSP UDP/RTP", fontSize = 12.sp, color = Color(0xFF94A3B8))
                                    Button(onClick = { doRunRtspUdpProbe() }, enabled = vpnRunning && !rtspUdpProbeRunning,
                                        modifier = Modifier.height(28.dp), contentPadding = PaddingValues(horizontal = 8.dp, vertical = 0.dp), colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF334155))) {
                                        Text(if (rtspUdpProbeRunning) "探测中" else "探测", fontSize = 11.sp)
                                    }
                                }
                                if (rtspUdpProbeText.isNotEmpty()) Text(rtspUdpProbeText, fontSize = 9.sp, color = Color(0xFF38BDF8), lineHeight = 13.sp, modifier = Modifier.padding(top = 2.dp))
                                if (rtcpFeedbackText.isNotEmpty()) Text(rtcpFeedbackText, fontSize = 9.sp, color = Color(0xFFFBBF24), lineHeight = 13.sp, modifier = Modifier.padding(top = 2.dp))

                                Spacer(Modifier.height(8.dp))
                                var debugExpanded by remember { mutableStateOf(true) }
                                val debugLogs by AppLog.logs.collectAsState()
                                val ds = rememberScrollState()
                                LaunchedEffect(debugLogs.size) { if (debugExpanded) ds.animateScrollTo(Int.MAX_VALUE) }
                                Row(modifier = Modifier.fillMaxWidth().clickable { debugExpanded = !debugExpanded }.padding(vertical = 4.dp), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                                    Text("Debug (${debugLogs.size})", fontSize = 10.sp, color = Color(0xFF64748B))
                                    Text(if (debugExpanded) "▲" else "▼", fontSize = 9.sp, color = Color(0xFF475569))
                                }
                                if (debugExpanded) {
                                    Box(modifier = Modifier.fillMaxWidth().heightIn(max = 200.dp).background(Color(0xFF020617), RoundedCornerShape(6.dp)).border(1.dp, Color(0xFF1E293B), RoundedCornerShape(6.dp))) {
                                        Column(modifier = Modifier.verticalScroll(ds).padding(6.dp)) {
                                            val recent = debugLogs.takeLast(50).reversed()
                                            if (recent.isEmpty()) Text("等待日志...", fontSize = 9.sp, color = Color(0xFF475569))
                                            recent.forEach { entry -> Text(entry.fullLine, fontSize = 9.sp, color = when (entry.level) { AppLog.Level.ERROR -> Color(0xFFEF4444); AppLog.Level.WARN -> Color(0xFFF59E0B); AppLog.Level.INFO -> Color(0xFF38BDF8); AppLog.Level.DEBUG -> Color(0xFF64748B) }, lineHeight = 13.sp, modifier = Modifier.padding(vertical = 1.dp)) }
                                        }
                                    }
                                    TextButton(onClick = { AppLog.clear() }, modifier = Modifier.height(22.dp), contentPadding = PaddingValues(horizontal = 6.dp, vertical = 0.dp)) { Text("清空", fontSize = 9.sp, color = Color(0xFF64748B)) }
                                }

                                Spacer(Modifier.height(16.dp)); HorizontalDivider(color = Color(0xFF1E293B)); Spacer(Modifier.height(12.dp))
                                SectionHdr("关于")
                                Text("TUN NAT Hub", fontSize = 14.sp, fontWeight = FontWeight.Bold, color = Color(0xFF38BDF8))
                                Text("App 版本: v${BuildConfig.VERSION_NAME}", fontSize = 11.sp, color = Color(0xFF94A3B8))
                                Text("V3s 固件: ${if (v3sVersion.isNotEmpty()) "v$v3sVersion" else "未连接 (需 VPN 隧道)"}", fontSize = 11.sp, color = if (v3sVersion.isNotEmpty()) Color(0xFF38BDF8) else Color(0xFFF59E0B))
                                Text("设备: ${Build.MANUFACTURER} ${Build.MODEL} · Android ${Build.VERSION.SDK_INT}", fontSize = 11.sp, color = Color(0xFF64748B))
                            }
                        }
                    }

                }
            }
        }
    }
}

