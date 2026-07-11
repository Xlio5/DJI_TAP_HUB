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
import android.os.ResultReceiver
import android.util.Log
import android.view.SurfaceView
import android.widget.FrameLayout
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
import androidx.compose.material.icons.filled.Settings
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
import kotlinx.coroutines.*
import org.easydarwin.video.Client
import org.easydarwin.video.EasyPlayerClient

/** Activity 与 Compose 共享的播放器引用，用于 onDestroy 时释放 */
private val playerHolder = java.util.concurrent.atomic.AtomicReference<EasyPlayerClient?>(null)

class MainActivity : ComponentActivity() {
    companion object {
        private const val TAG = "MainActivity"
        private const val USB_PERM_ACTION = "com.tunnathub.app.USB_PERM"
        // V3s 同线供电, 开机需 10-15s → 最多轮询 30 次 (每 2s = 60s)
        private const val USB_POLL_MAX = 30
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
        usbDevice = findUsbDevice()
        if (usbDevice != null) connectionState = "found"

        setContent {
            // ── Compose 内驱动 USB 轮询 + 自动连接 ──
            var polledDevice by remember { mutableStateOf<UsbDevice?>(usbDevice) }
            var pollState by remember { mutableStateOf(if (usbDevice != null) "found" else "scanning") }
            var pollCount by remember { mutableIntStateOf(0) }
            var autoConnected by remember { mutableStateOf(false) }

            LaunchedEffect(pollState) {
                if (pollState != "scanning") return@LaunchedEffect
                var count = 0
                while (count < USB_POLL_MAX) {
                    count++
                    pollCount = count
                    kotlinx.coroutines.delay(2000)
                    val dev = findUsbDevice()
                    if (dev != null) {
                        usbDevice = dev
                        polledDevice = dev
                        pollState = "found"
                        if (!autoConnected) {
                            autoConnected = true
                            startAuthFlow()
                        }
                        return@LaunchedEffect
                    }
                }
                pollState = "timeout"
            }

            TunNatHubApp(
                usbFound = polledDevice != null,
                vpnRunning = TunNatVpnService.isRunningState.value,
                connectionState = pollState,
                usbPollCount = pollCount,
                onVpnTap = {
                    if (TunNatVpnService.isRunningState.value) stopTunService()
                    else if (usbDevice != null) startAuthFlow()
                },
                onReconnect = {
                    stopTunService()
                    Handler(Looper.getMainLooper()).postDelayed({
                        usbDevice = findUsbDevice()
                        if (usbDevice != null) startAuthFlow()
                    }, 1500)
                }
            )
        }

        if (usbDevice != null) startAuthFlow()
    }

    override fun onDestroy() {
        super.onDestroy()
        playerHolder.getAndSet(null)?.stop()
        try { unregisterReceiver(usbReceiver) } catch (_: Exception) {}
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

private enum class Tab { VIDEO, CONFIG }

// ═══════════════════════════════════════════════════════
// 顶层：状态栏 + 导航 + 内容区
// ═══════════════════════════════════════════════════════

@Composable
fun TunNatHubApp(usbFound: Boolean, vpnRunning: Boolean, connectionState: String = "idle", usbPollCount: Int = 0, onVpnTap: () -> Unit, onReconnect: (() -> Unit)? = null) {
    val ctx = LocalContext.current
    val prefs = ctx.getSharedPreferences("tun_nat_hub", Context.MODE_PRIVATE)
    var selectedTab by remember { mutableStateOf(Tab.VIDEO) }

    fun fmtSize(bytes: Long): String = when {
        bytes > 1024 * 1024 -> " %.1fM".format(bytes / 1024f / 1024f)
        bytes > 1024 -> " %.0fK".format(bytes / 1024f)
        else -> " ${bytes}B"
    }

    val savedUrl = prefs.getString("rtsp_url", "rtsp://192.168.88.100:554/stream1")
        ?: "rtsp://192.168.88.100:554/stream1"
    var rtspUrl by remember { mutableStateOf(savedUrl) }
    var isPlaying by remember { mutableStateOf(false) }
    var statusText by remember { mutableStateOf("") }
    var resolutionText by remember { mutableStateOf("") }
    var surfaceViewRef by remember { mutableStateOf<SurfaceView?>(null) }
    var playerRef by remember { mutableStateOf<EasyPlayerClient?>(null) }

    // ── 心跳状态 ──
    var hbDaemon by remember { mutableStateOf(false) }
    var hbTty by remember { mutableStateOf(false) }
    var hbTun by remember { mutableStateOf(false) }
    var hbTime by remember { mutableStateOf("") }
    var hbCount by remember { mutableStateOf(0) }
    var hbBw by remember { mutableStateOf("0.0") }
    var hbTx by remember { mutableStateOf(0L) }
    var hbRx by remember { mutableStateOf(0L) }

    // ── 摄像头列表 ──
    data class CamInfo(val name: String, val url: String)
    var cameras by remember { mutableStateOf(listOf<CamInfo>()) }
    var selectedCam by remember { mutableStateOf(0) }

    // ── 端口转发 ──
    data class FwdInfo(val proto: String, val port: Int, val dest: String)
    var forwards by remember { mutableStateOf(listOf<FwdInfo>()) }
    var fwdProto by remember { mutableStateOf("udp") }
    var fwdExtPort by remember { mutableStateOf("") }
    var fwdDestPort by remember { mutableStateOf("") }
    var fwdDestIp by remember { mutableStateOf("10.0.0.2") }
    var fwdMsg by remember { mutableStateOf("") }

    // ── LAN 网段 ──
    val savedLanSubnet = prefs.getString("lan_subnet", "192.168.88.0") ?: "192.168.88.0"
    val savedLanPrefix = prefs.getInt("lan_prefix", 24)
    var needVpnReconnect by remember { mutableStateOf(false) }

    // ── 解码器选择 ──
    val savedCodec = remember { prefs.getString("forced_codec", "auto") ?: "auto" }
    LaunchedEffect(Unit) { EasyPlayerClient.setForcedCodec(savedCodec) }

    // 延迟测试
    var latencyText by remember { mutableStateOf("") }
    var testing by remember { mutableStateOf(false) }

    // ── HTTP POST ──
    fun apiPost(path: String, body: String) {
        kotlinx.coroutines.CoroutineScope(kotlinx.coroutines.Dispatchers.IO).launch {
            try {
                val url = java.net.URL("http://10.0.0.1:8080$path")
                val conn = url.openConnection() as java.net.HttpURLConnection
                conn.connectTimeout = 3000; conn.readTimeout = 3000
                conn.doOutput = true; conn.requestMethod = "POST"
                conn.setRequestProperty("Content-Type", "application/json")
                conn.outputStream.write(body.toByteArray())
                conn.inputStream.close()
            } catch (e: Exception) {
                android.util.Log.e("TunNatHub", "API POST $path 失败: ${e.javaClass.simpleName} ${e.message}")
            }
        }
    }

    // ── 心跳轮询 ──
    LaunchedEffect(vpnRunning) {
        if (!vpnRunning) { hbCount = 0; return@LaunchedEffect }
        while (vpnRunning) {
            kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
                try {
                    val text = java.net.URL("http://10.0.0.1:8080/api/heartbeat").openConnection()
                        .apply { connectTimeout = 2000; readTimeout = 2000 }
                        .getInputStream().bufferedReader().readText()
                    hbDaemon = text.contains("\"daemon\": true")
                    hbTty = text.contains("\"tty_ready\": true")
                    hbTun = text.contains("\"tun_up\": true")
                    hbBw = Regex("\"bandwidth_mbps\": \"([^\"]+)\"").find(text)?.groupValues?.get(1) ?: "0.0"
                    hbTx = Regex("\"tx_bytes\": (\\d+)").find(text)?.groupValues?.get(1)?.toLongOrNull() ?: 0L
                    hbRx = Regex("\"rx_bytes\": (\\d+)").find(text)?.groupValues?.get(1)?.toLongOrNull() ?: 0L
                    hbCount++
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
                val text = java.net.URL("http://10.0.0.1:8080/api/config").openConnection()
                    .apply { connectTimeout = 2000; readTimeout = 2000 }
                    .getInputStream().bufferedReader().readText()
                AppLog.d("TunNatHub", "获取 V3s 配置: OK (${text.length} bytes)")
                val camList = Regex("\"name\": \"([^\"]+)\"[^}]*\"url\": \"([^\"]+)\"").findAll(text).map {
                    CamInfo(it.groupValues[1], it.groupValues[2])
                }.toList()
                if (camList.isNotEmpty()) { cameras = camList; if (rtspUrl.isEmpty()) rtspUrl = camList[0].url }
                forwards = Regex("\"proto\": \"(\\w+)\"[^}]*\"port\": (\\d+)[^}]*\"dest\": \"([^\"]+)\"").findAll(text).map {
                    FwdInfo(it.groupValues[1], it.groupValues[2].toInt(), it.groupValues[3])
                }.toList()
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
            } catch (_: Exception) {}
        }
    }

    val receiver = remember {
        object : ResultReceiver(Handler(ctx.mainLooper)) {
            override fun onReceiveResult(code: Int, data: Bundle?) {
                when (code) {
                    EasyPlayerClient.RESULT_VIDEO_DISPLAYED -> {
                        val cn = EasyPlayerClient.getForcedCodec()
                        val ts = if (cn != "auto") cn.split(".").last().take(25)
                            else if ((data?.getInt(EasyPlayerClient.KEY_VIDEO_DECODE_TYPE, -1) ?: -1) == 1) "MediaCodec"
                            else "SW"
                        statusText = "播放中 [$ts]"; isPlaying = true
                        AppLog.i("Player", "解码器: $ts")
                    }
                    EasyPlayerClient.RESULT_VIDEO_SIZE -> {
                        resolutionText = "${data?.getInt(EasyPlayerClient.EXTRA_VIDEO_WIDTH, 0)}x${data?.getInt(EasyPlayerClient.EXTRA_VIDEO_HEIGHT, 0)}"
                    }
                    EasyPlayerClient.RESULT_TIMEOUT -> { statusText = "连接超时"; isPlaying = false }
                    EasyPlayerClient.RESULT_UNSUPPORTED_VIDEO -> { statusText = "编码不支持"; isPlaying = false }
                }
            }
        }
    }

    fun autoSyncSubnet(url: String) {
        val ipMatch = Regex("rtsp://(\\d+\\.\\d+\\.\\d+)\\.\\d+").find(url) ?: return
        val ns = "${ipMatch.groupValues[1]}.0"
        if (ns != (prefs.getString("lan_subnet", "192.168.88.0") ?: "192.168.88.0")) {
            prefs.edit().putString("lan_subnet", ns).putInt("lan_prefix", 24).apply()
            needVpnReconnect = true
            AppLog.w("TunNatHub", "网段自动同步 → $ns")
        }
    }

    fun togglePlay() {
        if (isPlaying) {
            playerRef?.stop(); playerRef = null; isPlaying = false; statusText = "已停止"
            playerHolder.set(null)
        } else {
            val sv = surfaceViewRef ?: return
            try {
                prefs.edit().putString("rtsp_url", rtspUrl).apply()
                autoSyncSubnet(rtspUrl)
                val client = EasyPlayerClient(ctx, sv.holder.surface, receiver)
                client.start(rtspUrl, Client.TRANSTYPE_TCP, 1,
                    Client.EASY_SDK_VIDEO_FRAME_FLAG or Client.EASY_SDK_AUDIO_FRAME_FLAG, "", "", null)
                playerRef = client; isPlaying = true; statusText = "连接中..."
                playerHolder.set(client)
            } catch (e: Exception) { Log.e("TunNatHub", "播放失败", e); statusText = "播放失败" }
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
                    // 左侧: USB● VPN● + 码率
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Surface(shape = CircleShape, color = if (usbFound) Color(0xFF22C55E) else Color(0xFFEF4444), modifier = Modifier.size(6.dp)) {}
                        Spacer(Modifier.width(3.dp))
                        Surface(shape = CircleShape, color = if (vpnRunning) Color(0xFF22C55E) else Color(0xFFEF4444), modifier = Modifier.size(6.dp)) {}
                        if (vpnRunning && hbCount > 0) {
                            Spacer(Modifier.width(8.dp))
                            Text("${hbBw} Mbps", fontSize = 12.sp, fontWeight = FontWeight.Medium, color = Color(0xFF38BDF8))
                            Spacer(Modifier.width(10.dp))
                            Text("Tx${fmtSize(hbTx)} Rx${fmtSize(hbRx)}", fontSize = 10.sp, color = Color(0xFF64748B))
                        } else if (!vpnRunning) {
                            Spacer(Modifier.width(8.dp))
                            val st = when (connectionState) {
                                "scanning" -> if (usbPollCount > 0) "搜索中 (${usbPollCount}s)" else "搜索中..."
                                "timeout" -> "未找到设备"
                                "found" -> "已发现，点击连接"
                                else -> "插入 USB 线"
                            }
                            Text(st, fontSize = 11.sp, color = Color(0xFF64748B))
                        } else {
                            Spacer(Modifier.width(8.dp))
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
                        IconButton(onClick = { selectedTab = Tab.CONFIG }, modifier = Modifier.size(40.dp)) {
                            Icon(Icons.Filled.Settings, "配置",
                                tint = if (selectedTab == Tab.CONFIG) Color(0xFF38BDF8) else Color(0xFF475569),
                                modifier = Modifier.size(22.dp))
                        }
                        Text("配置", fontSize = 9.sp, color = if (selectedTab == Tab.CONFIG) Color(0xFF38BDF8) else Color(0xFF475569))
                        Spacer(Modifier.weight(1f))
                        Text("v${BuildConfig.VERSION_NAME}", fontSize = 9.sp, color = Color(0xFF475569))
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
                                AndroidView(
                                    factory = { SurfaceView(it).apply { surfaceViewRef = this } },
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

                    // 配置页覆盖层
                    if (selectedTab == Tab.CONFIG) {
                        val scrollState = rememberScrollState()
                        Surface(modifier = Modifier.fillMaxSize(), color = Color(0xFF0F172A)) {
                            Column(modifier = Modifier.fillMaxSize().verticalScroll(scrollState).padding(16.dp)) {
                                @Composable fun SectionHdr(t: String) { Text(t, fontSize = 13.sp, fontWeight = FontWeight.Bold, color = Color(0xFF38BDF8), modifier = Modifier.padding(bottom = 6.dp)) }

                                SectionHdr("网段配置")
                                Text("修改后需断开并重连 VPN 生效", fontSize = 9.sp, color = Color(0xFF475569))
                                Spacer(Modifier.height(6.dp))
                                var lanSubnet by remember { mutableStateOf(savedLanSubnet) }
                                var lanPrefixStr by remember { mutableStateOf(savedLanPrefix.toString()) }
                                var advSaved by remember { mutableStateOf(false) }
                                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp), verticalAlignment = Alignment.CenterVertically) {
                                    Box(modifier = Modifier.weight(1f).height(36.dp).background(Color(0xFF0F172A), RoundedCornerShape(6.dp)).border(1.dp, Color(0xFF334155), RoundedCornerShape(6.dp)).padding(horizontal = 10.dp), contentAlignment = Alignment.CenterStart) {
                                        BasicTextField(value = lanSubnet, onValueChange = { lanSubnet = it; advSaved = false }, singleLine = true,
                                            textStyle = androidx.compose.ui.text.TextStyle(fontSize = 13.sp, color = Color(0xFFE2E8F0)), cursorBrush = androidx.compose.ui.graphics.SolidColor(Color(0xFF38BDF8)), modifier = Modifier.fillMaxWidth())
                                    }
                                    Text("/", fontSize = 14.sp, color = Color(0xFF64748B))
                                    Box(modifier = Modifier.width(40.dp).height(36.dp).background(Color(0xFF0F172A), RoundedCornerShape(6.dp)).border(1.dp, Color(0xFF334155), RoundedCornerShape(6.dp)).padding(horizontal = 10.dp), contentAlignment = Alignment.Center) {
                                        BasicTextField(value = lanPrefixStr, onValueChange = { lanPrefixStr = it; advSaved = false }, singleLine = true,
                                            textStyle = androidx.compose.ui.text.TextStyle(fontSize = 13.sp, color = Color(0xFFE2E8F0)), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), modifier = Modifier.fillMaxWidth())
                                    }
                                }
                                Spacer(Modifier.height(6.dp))
                                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                                    Button(onClick = {
                                        val prefix = lanPrefixStr.toIntOrNull()
                                        if (prefix == null || prefix < 8 || prefix > 30) { lanPrefixStr = savedLanPrefix.toString(); return@Button }
                                        prefs.edit().putString("lan_subnet", lanSubnet).putInt("lan_prefix", prefix).apply(); advSaved = true
                                    }, modifier = Modifier.height(30.dp), contentPadding = PaddingValues(horizontal = 10.dp, vertical = 0.dp), colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF2563EB))) { Text("保存", fontSize = 11.sp) }
                                    Button(onClick = { lanSubnet = "192.168.88.0"; lanPrefixStr = "24"; prefs.edit().putString("lan_subnet", "192.168.88.0").putInt("lan_prefix", 24).apply(); advSaved = true },
                                        modifier = Modifier.height(30.dp), contentPadding = PaddingValues(horizontal = 10.dp, vertical = 0.dp), colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF334155))) { Text("默认", fontSize = 10.sp) }
                                }
                                if (advSaved) Text("已保存, 重连 VPN 生效", fontSize = 9.sp, color = Color(0xFF22C55E), modifier = Modifier.padding(top = 4.dp))

                                Spacer(Modifier.height(16.dp)); HorizontalDivider(color = Color(0xFF1E293B)); Spacer(Modifier.height(12.dp))
                                SectionHdr("解码器")
                                var selectedCodec by remember { mutableStateOf(EasyPlayerClient.getForcedCodec()) }
                                var codecList by remember { mutableStateOf(listOf("auto")) }
                                var codecDropdown by remember { mutableStateOf(false) }
                                var codecSaved by remember { mutableStateOf(false) }
                                LaunchedEffect(Unit) { try { codecList = listOf("auto") + EasyPlayerClient.listAvailableDecoders() } catch (_: Exception) {} }
                                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                                    Box(modifier = Modifier.weight(1f)) {
                                        Row(modifier = Modifier.fillMaxWidth().height(32.dp).background(Color(0xFF0F172A), RoundedCornerShape(6.dp)).border(1.dp, Color(0xFF334155), RoundedCornerShape(6.dp)).clickable { codecDropdown = !codecDropdown }.padding(horizontal = 10.dp), verticalAlignment = Alignment.CenterVertically) {
                                            Text(selectedCodec.let { if (it == "auto") "auto" else if (it.contains("low_latency")) it + " ⚡" else it }, fontSize = 10.sp, color = if (selectedCodec == "auto") Color(0xFF22C55E) else Color(0xFFF59E0B), maxLines = 1, overflow = TextOverflow.Ellipsis, modifier = Modifier.weight(1f))
                                            Text(if (codecDropdown) "▲" else "▼", fontSize = 9.sp, color = Color(0xFF64748B))
                                        }
                                        DropdownMenu(expanded = codecDropdown, onDismissRequest = { codecDropdown = false }, modifier = Modifier.background(Color(0xFF1E293B))) {
                                            codecList.forEach { c -> DropdownMenuItem(text = { Text(c, fontSize = 10.sp, color = Color(0xFFE2E8F0)) }, onClick = { selectedCodec = c; codecDropdown = false; codecSaved = false }, modifier = Modifier.background(if (c == selectedCodec) Color(0xFF334155) else Color(0xFF1E293B))) }
                                        }
                                    }
                                    Spacer(Modifier.width(6.dp))
                                    Button(onClick = { EasyPlayerClient.setForcedCodec(selectedCodec); codecSaved = true; prefs.edit().putString("forced_codec", selectedCodec).apply() },
                                        modifier = Modifier.height(30.dp), contentPadding = PaddingValues(horizontal = 8.dp, vertical = 0.dp), colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF2563EB))) { Text("应用", fontSize = 10.sp) }
                                }
                                if (codecSaved) Text("解码器已切换, 重启播放生效", fontSize = 9.sp, color = Color(0xFFF59E0B), modifier = Modifier.padding(top = 2.dp))

                                Spacer(Modifier.height(16.dp)); HorizontalDivider(color = Color(0xFF1E293B)); Spacer(Modifier.height(12.dp))
                                SectionHdr("诊断")
                                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                                    Text("隧道延迟", fontSize = 12.sp, color = Color(0xFF94A3B8))
                                    Button(onClick = {
                                        if (!testing && vpnRunning) {
                                            testing = true; latencyText = "测试中..."
                                            Thread {
                                                val rtts = mutableListOf<Double>(); var drops = 0
                                                try {
                                                    for (i in 0 until 10) { try { val t0 = System.nanoTime(); val s = java.net.Socket(); s.connect(java.net.InetSocketAddress("10.0.0.1", 9999), 3000); rtts.add((System.nanoTime() - t0) / 1_000_000.0); s.close() } catch (_: Exception) { drops++ } }
                                                    if (rtts.isNotEmpty()) { rtts.sort(); latencyText = "%.1f/%.1f/%.1f ms (丢$drops)".format(rtts.average(), rtts[rtts.size / 2], rtts[(rtts.size * 0.95).toInt()]) } else latencyText = "全部丢包 ($drops/10)"
                                                } catch (_: Exception) { latencyText = "失败" }
                                                testing = false
                                            }.start()
                                        }
                                    }, enabled = vpnRunning && !testing, modifier = Modifier.height(28.dp), contentPadding = PaddingValues(horizontal = 8.dp, vertical = 0.dp), colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF334155))) { Text(if (testing) "⏳" else "⏱", fontSize = 11.sp) }
                                }
                                if (latencyText.isNotEmpty()) Text(latencyText, fontSize = 10.sp, color = Color(0xFF38BDF8), modifier = Modifier.padding(top = 2.dp))

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
                                Text("版本: v${BuildConfig.VERSION_NAME}", fontSize = 11.sp, color = Color(0xFF94A3B8))
                                Text("设备: ${Build.MANUFACTURER} ${Build.MODEL} · Android ${Build.VERSION.SDK_INT}", fontSize = 11.sp, color = Color(0xFF64748B))
                            }
                        }
                    }
                }
            }
        }
    }
}

