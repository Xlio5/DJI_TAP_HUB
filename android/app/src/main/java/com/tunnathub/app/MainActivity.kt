/**
 * MainActivity.kt — VPN 控制 + RTSP 播放器
 * 横屏优化：左侧控制栏 + 右侧全屏视频
 */

package com.tunnathub.app

import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.hardware.usb.UsbDevice
import android.hardware.usb.UsbManager
import android.net.VpnService
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.ResultReceiver
import android.util.Log
import android.view.SurfaceHolder
import android.view.SurfaceView
import android.widget.FrameLayout
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.PowerSettingsNew
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material.icons.filled.Usb
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.viewinterop.AndroidView
import com.tunnathub.app.BuildConfig
import com.tunnathub.app.service.TunNatVpnService
import com.tunnathub.app.usb.UsbBridge
import kotlinx.coroutines.*
import org.easydarwin.video.EasyPlayerClient

class MainActivity : ComponentActivity() {
    companion object {
        private const val TAG = "MainActivity"
        private const val USB_PERM_ACTION = "com.tunnathub.app.USB_PERM"
    }
    private var usbDevice: UsbDevice? = null
    private var isVpnRunning = mutableStateOf(false)

    private val usbReceiver = object : BroadcastReceiver() {
        override fun onReceive(ctx: Context, intent: Intent) {
            if (USB_PERM_ACTION != intent.action) return
            if (intent.getBooleanExtra(UsbManager.EXTRA_PERMISSION_GRANTED, false)) {
                requestVpn()
            }
        }
    }

    private val vpnLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == RESULT_OK) startTunService()
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        registerReceiver(usbReceiver, IntentFilter(USB_PERM_ACTION), Context.RECEIVER_NOT_EXPORTED)
        usbDevice = findUsbDevice()

        setContent {
            TunNatHubApp(
                usbFound = usbDevice != null,
                vpnRunning = isVpnRunning.value,
                onVpnTap = {
                    if (isVpnRunning.value) stopTunService()
                    else startAuthFlow()
                }
            )
        }

        if (usbDevice != null) startAuthFlow()
    }

    override fun onResume() {
        super.onResume()
        isVpnRunning.value = TunNatVpnService.isRunning
    }

    override fun onDestroy() {
        super.onDestroy()
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
        val i = Intent(this, TunNatVpnService::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) startForegroundService(i) else startService(i)
        isVpnRunning.value = true
    }

    private fun stopTunService() {
        stopService(Intent(this, TunNatVpnService::class.java))
        isVpnRunning.value = false
    }

    private fun findUsbDevice(): UsbDevice? {
        val um = getSystemService(USB_SERVICE) as UsbManager
        for ((_, d) in um.deviceList)
            if (d.vendorId == UsbBridge.USB_VID && d.productId == UsbBridge.USB_PID) return d
        return null
    }
}

// ═══════════════════════════════════════════════════════
// 横屏主界面：可收起侧栏 + 全屏视频
// ═══════════════════════════════════════════════════════

@Composable
fun TunNatHubApp(usbFound: Boolean, vpnRunning: Boolean, onVpnTap: () -> Unit) {
    val ctx = LocalContext.current
    val prefs = ctx.getSharedPreferences("tun_nat_hub", Context.MODE_PRIVATE)

    val savedUrl = prefs.getString("rtsp_url", "rtsp://192.168.88.100:554/stream1")
        ?: "rtsp://192.168.88.100:554/stream1"
    var rtspUrl by remember { mutableStateOf(savedUrl) }
    var isPlaying by remember { mutableStateOf(false) }
    var statusText by remember { mutableStateOf("") }
    var resolutionText by remember { mutableStateOf("") }
    var surfaceViewRef by remember { mutableStateOf<SurfaceView?>(null) }
    var playerRef by remember { mutableStateOf<EasyPlayerClient?>(null) }
    var sidebarExpanded by remember { mutableStateOf(true) }

    // ── 心跳状态 ──
    var hbDaemon by remember { mutableStateOf(false) }
    var hbTty by remember { mutableStateOf(false) }
    var hbTun by remember { mutableStateOf(false) }
    var hbTime by remember { mutableStateOf("") }
    var hbCount by remember { mutableStateOf(0) }
    var hbBw by remember { mutableStateOf("0.0") }  // Mbps
    var hbTx by remember { mutableStateOf(0L) }     // total bytes
    var hbRx by remember { mutableStateOf(0L) }

    // ── 摄像头列表 ──
    data class CamInfo(val name: String, val url: String)
    var cameras by remember { mutableStateOf(listOf<CamInfo>()) }
    var selectedCam by remember { mutableStateOf(0) }

    // ── 端口转发 ──
    data class FwdInfo(val proto: String, val port: Int, val dest: String)
    var forwards by remember { mutableStateOf(listOf<FwdInfo>()) }
    var fwdProto by remember { mutableStateOf("udp") }
    var fwdPort by remember { mutableStateOf("") }
    var fwdDest by remember { mutableStateOf("10.0.0.2") }

    // ── HTTP POST helper (协程 IO 线程, 跟随 Composable 生命周期) ──
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
            } catch (_: Exception) {}
        }
    }

    // ── 心跳轮询 (仅通过USB隧道 10.0.0.1:8080) ──
    LaunchedEffect(vpnRunning) {
        if (!vpnRunning) { hbCount = 0; return@LaunchedEffect }
        while (vpnRunning) {
            try {
                val url = java.net.URL("http://10.0.0.1:8080/api/heartbeat")
                val conn = url.openConnection() as java.net.HttpURLConnection
                conn.connectTimeout = 2000; conn.readTimeout = 2000
                val text = conn.inputStream.bufferedReader().readText()
                hbDaemon = text.contains("\"daemon\": true")
                hbTty = text.contains("\"tty_ready\": true")
                hbTun = text.contains("\"tun_up\": true")
                hbTime = (Regex("\"uptime_since\": \"([^\"]+)\"").find(text)?.groupValues?.get(1)) ?: ""
                hbBw = (Regex("\"bandwidth_mbps\": \"([^\"]+)\"").find(text)?.groupValues?.get(1)) ?: "0.0"
                val mTx = Regex("\"tx_bytes\": (\\d+)").find(text)?.groupValues?.get(1)?.toLongOrNull() ?: 0L
                val mRx = Regex("\"rx_bytes\": (\\d+)").find(text)?.groupValues?.get(1)?.toLongOrNull() ?: 0L
                hbTx = mTx; hbRx = mRx; hbCount++
            } catch (_: Exception) { hbDaemon = false; hbTty = false; hbTun = false }
            kotlinx.coroutines.delay(5000)
        }
    }

    // ── 加载摄像头列表 + 端口转发 ──
    LaunchedEffect(vpnRunning) {
        if (!vpnRunning) return@LaunchedEffect
        try {
            val url = java.net.URL("http://10.0.0.1:8080/api/config")
            val conn = url.openConnection() as java.net.HttpURLConnection
            conn.connectTimeout = 2000
            conn.readTimeout = 2000
            val text = conn.inputStream.bufferedReader().readText()
            // Parse cameras
            val camList = mutableListOf<CamInfo>()
            val camPattern = Regex("\"name\": \"([^\"]+)\"[^}]*\"url\": \"([^\"]+)\"")
            camPattern.findAll(text).forEach { m ->
                camList.add(CamInfo(m.groupValues[1], m.groupValues[2]))
            }
            if (camList.isNotEmpty()) {
                cameras = camList
                if (rtspUrl.isEmpty()) rtspUrl = camList[0].url
            }
            // Parse port forwards
            val fwdList = mutableListOf<FwdInfo>()
            val fwdPattern = Regex("\"proto\": \"(\\w+)\"[^}]*\"port\": (\\d+)[^}]*\"dest\": \"([^\"]+)\"")
            fwdPattern.findAll(text).forEach { m ->
                fwdList.add(FwdInfo(m.groupValues[1], m.groupValues[2].toInt(), m.groupValues[3]))
            }
            forwards = fwdList
        } catch (_: Exception) {}
    }

    val receiver = remember {
        object : ResultReceiver(Handler(ctx.mainLooper)) {
            override fun onReceiveResult(code: Int, data: Bundle?) {
                when (code) {
                    EasyPlayerClient.RESULT_VIDEO_DISPLAYED -> { statusText = "播放中"; isPlaying = true }
                    EasyPlayerClient.RESULT_VIDEO_SIZE -> {
                        val w = data?.getInt(EasyPlayerClient.EXTRA_VIDEO_WIDTH, 0) ?: 0
                        val h = data?.getInt(EasyPlayerClient.EXTRA_VIDEO_HEIGHT, 0) ?: 0
                        resolutionText = "${w}x${h}"
                    }
                    EasyPlayerClient.RESULT_TIMEOUT -> { statusText = "连接超时"; isPlaying = false }
                    EasyPlayerClient.RESULT_EVENT -> {
                        val msg = data?.getString("event-msg")
                        if (msg != null) statusText = msg
                    }
                    EasyPlayerClient.RESULT_UNSUPPORTED_VIDEO -> { statusText = "编码不支持"; isPlaying = false }
                }
            }
        }
    }

    fun togglePlay() {
        if (isPlaying) {
            playerRef?.stop(); playerRef = null; isPlaying = false; statusText = "已停止"
        } else {
            val sv = surfaceViewRef ?: return
            try {
                prefs.edit().putString("rtsp_url", rtspUrl).apply()
                val client = EasyPlayerClient(ctx, sv.holder.surface, receiver)
                client.start(rtspUrl, org.easydarwin.video.Client.TRANSTYPE_TCP, 1,
                    org.easydarwin.video.Client.EASY_SDK_VIDEO_FRAME_FLAG or
                    org.easydarwin.video.Client.EASY_SDK_AUDIO_FRAME_FLAG, "", "", null)
                playerRef = client; isPlaying = true; statusText = "连接中..."
            } catch (e: Exception) { Log.e("TunNatHub", "播放失败", e); statusText = "播放失败" }
        }
    }

    MaterialTheme(colorScheme = darkColorScheme(
        background = Color(0xFF0F172A), surface = Color(0xFF1E293B), primary = Color(0xFF38BDF8),
        onBackground = Color(0xFFE2E8F0), onSurface = Color(0xFFE2E8F0), surfaceVariant = Color(0xFF1E293B)
    )) {
        Row(modifier = Modifier.fillMaxSize().background(Color(0xFF0F172A))) {

            // ═══ 侧边栏：展开时 340dp，收起时隐藏 ═══
            if (sidebarExpanded) {
                Surface(modifier = Modifier.width(340.dp).fillMaxHeight(),
                    color = Color(0xFF111827), shadowElevation = 8.dp
                ) {
                    Column(modifier = Modifier.fillMaxHeight().padding(16.dp), verticalArrangement = Arrangement.Top) {
                        // 标题行 + 折叠按钮
                        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Column {
                                Text("TUN NAT HUB", fontSize = 20.sp, fontWeight = FontWeight.Bold, color = Color(0xFF38BDF8))
                                Text("USB 隧道 · 视频传输", fontSize = 11.sp, color = Color(0xFF64748B))
                            }
                            TextButton(onClick = { sidebarExpanded = false }, modifier = Modifier.size(32.dp),
                                contentPadding = PaddingValues(0.dp)
                            ) { Text("◀", fontSize = 14.sp, color = Color(0xFF94A3B8)) }
                        }

                        Spacer(Modifier.height(12.dp))

                        // USB 状态
                        Row(modifier = Modifier.padding(bottom = 8.dp), verticalAlignment = Alignment.CenterVertically) {
                            Surface(modifier = Modifier.size(8.dp), shape = androidx.compose.foundation.shape.CircleShape,
                                color = if (usbFound) Color(0xFF22C55E) else Color(0xFFEF4444)) {}
                            Spacer(Modifier.width(8.dp))
                            Text(if (usbFound) "USB 已检测" else "USB 未连接", fontSize = 13.sp,
                                color = if (usbFound) Color(0xFF22C55E) else Color(0xFF94A3B8))
                        }

                        // VPN 状态 + 按钮
                        Row(modifier = Modifier.fillMaxWidth().padding(bottom = 12.dp),
                            verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Surface(modifier = Modifier.size(8.dp), shape = androidx.compose.foundation.shape.CircleShape,
                                    color = if (vpnRunning) Color(0xFF22C55E) else Color(0xFFEF4444)) {}
                                Spacer(Modifier.width(8.dp))
                                Text(if (vpnRunning) "VPN 已连接" else "VPN 未连接", fontSize = 13.sp,
                                    color = if (vpnRunning) Color(0xFF22C55E) else Color(0xFF94A3B8))
                            }
                            Button(onClick = onVpnTap, enabled = usbFound, modifier = Modifier.height(34.dp),
                                contentPadding = PaddingValues(horizontal = 16.dp, vertical = 2.dp),
                                colors = ButtonDefaults.buttonColors(
                                    containerColor = if (vpnRunning) Color(0xFFDC2626) else Color(0xFF2563EB))
                            ) { Text(if (vpnRunning) "断开" else "连接", fontSize = 13.sp) }
                        }

                        HorizontalDivider(color = Color(0xFF1E293B))

                        // RTSP 地址
                        Text("RTSP 摄像头地址", fontSize = 12.sp, color = Color(0xFF94A3B8),
                            modifier = Modifier.padding(top = 8.dp, bottom = 4.dp))
                        OutlinedTextField(value = rtspUrl, onValueChange = { rtspUrl = it },
                            modifier = Modifier.fillMaxWidth(), singleLine = true,
                            textStyle = LocalTextStyle.current.copy(fontSize = 13.sp, color = Color(0xFFE2E8F0)),
                            colors = OutlinedTextFieldDefaults.colors(focusedBorderColor = Color(0xFF38BDF8),
                                unfocusedBorderColor = Color(0xFF334155), cursorColor = Color(0xFF38BDF8)),
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri, imeAction = ImeAction.Done))

                        Spacer(Modifier.height(8.dp))

                        // 播放/停止按钮
                        Button(onClick = { togglePlay() }, modifier = Modifier.fillMaxWidth().height(40.dp),
                            colors = ButtonDefaults.buttonColors(
                                containerColor = if (isPlaying) Color(0xFFDC2626) else Color(0xFF16A34A))
                        ) { Text(if (isPlaying) "■ 停止播放" else "▶ 开始播放", fontSize = 14.sp, fontWeight = FontWeight.Medium) }

                        Spacer(Modifier.height(10.dp))

                        // 状态
                        if (statusText.isNotEmpty()) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                if (isPlaying) { Surface(modifier = Modifier.size(6.dp),
                                    shape = androidx.compose.foundation.shape.CircleShape, color = Color(0xFF22C55E)) {}
                                    Spacer(Modifier.width(6.dp)) }
                                Text(statusText, fontSize = 12.sp, color = if (isPlaying) Color(0xFF22C55E) else Color(0xFF94A3B8))
                            }
                        }
                        if (resolutionText.isNotEmpty())
                            Text(resolutionText, fontSize = 11.sp, color = Color(0xFF94A3B8))

                        Spacer(Modifier.height(8.dp))
                        HorizontalDivider(color = Color(0xFF1E293B))

                        // ── 延迟测试 ──
                        var latencyText by remember { mutableStateOf("") }
                        var testing by remember { mutableStateOf(false) }
                        Row(modifier = Modifier.fillMaxWidth().padding(top = 6.dp),
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Text("隧道延迟", fontSize = 11.sp, color = Color(0xFF94A3B8))
                            Button(onClick = {
                                if (!testing && vpnRunning) {
                                    testing = true; latencyText = "测试中..."
                                    Thread {
                                        val rtts = mutableListOf<Double>()
                                        var drops = 0
                                        try {
                                            for (i in 0 until 10) {
                                                try {
                                                    val t0 = System.nanoTime()
                                                    val s = java.net.Socket()
                                                    s.connect(java.net.InetSocketAddress("10.0.0.1", 9999), 3000)
                                                    val t1 = System.nanoTime()
                                                    s.close()
                                                    rtts.add((t1 - t0) / 1_000_000.0)
                                                } catch (_: Exception) { drops++ }
                                            }
                                            if (rtts.isNotEmpty()) {
                                                rtts.sort()
                                                val avg = rtts.average()
                                                val p50 = rtts[rtts.size / 2]
                                                val p95 = rtts[(rtts.size * 0.95).toInt()]
                                                latencyText = "%.1f/%.1f/%.1f ms (avg/p50/p95, 丢包=$drops)".format(avg, p50, p95)
                                            } else { latencyText = "全部丢包 ($drops/10)" }
                                        } catch (e: Exception) { latencyText = "失败: ${e.message}" }
                                        testing = false
                                    }.start()
                                }
                            }, enabled = vpnRunning && !testing, modifier = Modifier.height(30.dp),
                                contentPadding = PaddingValues(horizontal = 10.dp, vertical = 0.dp),
                                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF334155))
                            ) { Text(if (testing) "⏳" else "⏱ 测延迟", fontSize = 11.sp) }
                        }
                        if (latencyText.isNotEmpty())
                            Text(latencyText, fontSize = 10.sp, color = Color(0xFF38BDF8), modifier = Modifier.padding(top = 2.dp))

                        // ── 心跳状态 (USB隧道 10.0.0.1:8080) ──
                        Spacer(Modifier.height(6.dp))
                        HorizontalDivider(color = Color(0xFF1E293B))
                        Spacer(Modifier.height(4.dp))
                        if (vpnRunning && hbCount > 0) {
                            Text("❤️ 链路状态 · ${hbBw} Mbps", fontSize = 11.sp, color = Color(0xFF94A3B8))
                            Spacer(Modifier.height(2.dp))
                            Row(modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp)) {
                                Text("Tx ${if (hbTx > 1024*1024) "%.1f MB".format(hbTx/1024f/1024f) else "%.0f KB".format(hbTx/1024f)}" +
                                    " | Rx ${if (hbRx > 1024*1024) "%.1f MB".format(hbRx/1024f/1024f) else "%.0f KB".format(hbRx/1024f)}",
                                    fontSize = 9.sp, color = Color(0xFF64748B))
                            }
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Surface(modifier = Modifier.size(6.dp), shape = androidx.compose.foundation.shape.CircleShape,
                                    color = if (hbDaemon) Color(0xFF22C55E) else Color(0xFFEF4444)) {}
                                Spacer(Modifier.width(4.dp))
                                Text(if (hbDaemon) "Daemon" else "Daemon 离线", fontSize = 10.sp,
                                    color = if (hbDaemon) Color(0xFF22C55E) else Color(0xFFEF4444))
                            }
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Surface(modifier = Modifier.size(6.dp), shape = androidx.compose.foundation.shape.CircleShape,
                                    color = if (hbTty) Color(0xFF22C55E) else Color(0xFFEF4444)) {}
                                Spacer(Modifier.width(4.dp))
                                Text(if (hbTty) "ttyGS0" else "ttyGS0 未检测", fontSize = 10.sp,
                                    color = if (hbTty) Color(0xFF22C55E) else Color(0xFFEF4444))
                            }
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Surface(modifier = Modifier.size(6.dp), shape = androidx.compose.foundation.shape.CircleShape,
                                    color = if (hbTun) Color(0xFF22C55E) else Color(0xFFEF4444)) {}
                                Spacer(Modifier.width(4.dp))
                                Text(if (hbTun) "tun_hub" else "tun_hub DOWN", fontSize = 10.sp,
                                    color = if (hbTun) Color(0xFF22C55E) else Color(0xFFEF4444))
                            }
                        } else if (vpnRunning) {
                            Text("❤️ 链路状态 · 轮询中...", fontSize = 11.sp, color = Color(0xFF94A3B8))
                            Spacer(Modifier.height(2.dp))
                            Text("首次轮询将在几秒后完成", fontSize = 9.sp, color = Color(0xFF64748B))
                        }

                        // ── 端口转发 ──
                        Spacer(Modifier.height(6.dp))
                        HorizontalDivider(color = Color(0xFF1E293B))
                        Spacer(Modifier.height(4.dp))
                        Text("🔀 端口转发 (外网→DJI)", fontSize = 11.sp, color = Color(0xFF94A3B8))
                        Spacer(Modifier.height(4.dp))
                        // 添加表单
                        Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(4.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            TextButton(onClick = {
                                fwdProto = if (fwdProto == "udp") "tcp" else "udp"
                            }, modifier = Modifier.height(26.dp), contentPadding = PaddingValues(4.dp, 0.dp)) {
                                Text(fwdProto.uppercase(), fontSize = 10.sp, color = Color(0xFF38BDF8))
                            }
                            OutlinedTextField(value = fwdPort, onValueChange = { fwdPort = it },
                                modifier = Modifier.width(50.dp).height(40.dp), singleLine = true,
                                textStyle = LocalTextStyle.current.copy(fontSize = 10.sp, color = Color(0xFFE2E8F0)),
                                colors = OutlinedTextFieldDefaults.colors(focusedBorderColor = Color(0xFF38BDF8), unfocusedBorderColor = Color(0xFF334155)),
                                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                                placeholder = { Text("端口", fontSize = 9.sp, color = Color(0xFF475569)) })
                            OutlinedTextField(value = fwdDest, onValueChange = { fwdDest = it },
                                modifier = Modifier.width(80.dp).height(40.dp), singleLine = true,
                                textStyle = LocalTextStyle.current.copy(fontSize = 10.sp, color = Color(0xFFE2E8F0)),
                                colors = OutlinedTextFieldDefaults.colors(focusedBorderColor = Color(0xFF38BDF8), unfocusedBorderColor = Color(0xFF334155)),
                                placeholder = { Text("目标IP", fontSize = 9.sp, color = Color(0xFF475569)) })
                            Button(onClick = {
                                val port = fwdPort.toIntOrNull() ?: return@Button
                                if (port < 1 || port > 65535) return@Button
                                val body = """{"proto":"$fwdProto","port":$port,"dest":"$fwdDest"}"""
                                apiPost("/api/forward/add", body)
                                fwdPort = ""
                                // Optimistic update
                                forwards = forwards + FwdInfo(fwdProto, port, fwdDest)
                            }, modifier = Modifier.height(28.dp), contentPadding = PaddingValues(4.dp, 0.dp),
                                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF2563EB))
                            ) { Text("＋", fontSize = 11.sp) }
                        }
                        // 规则列表
                        if (forwards.isEmpty()) {
                            Text("暂无转发规则", fontSize = 9.sp, color = Color(0xFF475569),
                                modifier = Modifier.padding(start = 2.dp, top = 2.dp))
                        } else {
                            forwards.forEach { f ->
                                Row(modifier = Modifier.fillMaxWidth().padding(vertical = 1.dp),
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Text("${f.proto.uppercase()} :${f.port} → ${f.dest}",
                                        fontSize = 10.sp, color = Color(0xFF94A3B8),
                                        modifier = Modifier.weight(1f))
                                    TextButton(onClick = {
                                        apiPost("/api/forward/del", """{"port":${f.port}}""")
                                        forwards = forwards.filter { it.port != f.port }
                                    }, modifier = Modifier.height(20.dp), contentPadding = PaddingValues(2.dp, 0.dp)
                                    ) { Text("✕", fontSize = 9.sp, color = Color(0xFFEF4444)) }
                                }
                            }
                        }

                        Spacer(modifier = Modifier.weight(1f))

                        // ── 摄像头切换 ──
                        if (cameras.isNotEmpty()) {
                            Text("📹 摄像头", fontSize = 10.sp, color = Color(0xFF94A3B8))
                            cameras.forEachIndexed { i, c ->
                                Row(
                                    modifier = Modifier.fillMaxWidth().padding(vertical = 1.dp),
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Surface(modifier = Modifier.size(6.dp), shape = androidx.compose.foundation.shape.CircleShape,
                                        color = if (i == selectedCam) Color(0xFF38BDF8) else Color(0xFF334155)) {}
                                    Spacer(Modifier.width(4.dp))
                                    Text(c.name, fontSize = 10.sp,
                                        color = if (i == selectedCam) Color(0xFF38BDF8) else Color(0xFF64748B),
                                        modifier = Modifier.weight(1f))
                                    if (i != selectedCam) {
                                        TextButton(onClick = { selectedCam = i; rtspUrl = cameras[i].url },
                                            modifier = Modifier.height(20.dp), contentPadding = PaddingValues(4.dp, 0.dp)
                                        ) { Text("切", fontSize = 9.sp, color = Color(0xFF38BDF8)) }
                                    }
                                }
                            }
                            Spacer(Modifier.height(4.dp))
                        }

                        HorizontalDivider(color = Color(0xFF1E293B), modifier = Modifier.padding(vertical = 8.dp))
                        Text("RK3588: 192.168.88.66", fontSize = 10.sp, color = Color(0xFF475569))
                        Text("TUN: 10.0.0.0/24", fontSize = 10.sp, color = Color(0xFF475569))
                        Text("VID 0x0BDA PID 0x8812", fontSize = 10.sp, color = Color(0xFF475569))
                        Spacer(Modifier.height(4.dp))
                        Text("v${BuildConfig.VERSION_NAME}", fontSize = 10.sp, color = Color(0xFF38BDF8))
                    }
                }
            }

            // ═══ 视频区域 ═══
            Box(modifier = Modifier.weight(1f).fillMaxHeight()) {
                Surface(modifier = Modifier.fillMaxHeight().padding(4.dp), color = Color(0xFF020617),
                    shape = androidx.compose.foundation.shape.RoundedCornerShape(8.dp)
                ) {
                    Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        AndroidView(
                            factory = { SurfaceView(it).apply { surfaceViewRef = this } },
                            modifier = Modifier.fillMaxWidth(0.94f).aspectRatio(16f / 9f),
                            update = { sv -> sv.layoutParams = FrameLayout.LayoutParams(
                                FrameLayout.LayoutParams.MATCH_PARENT, FrameLayout.LayoutParams.MATCH_PARENT
                            ).apply { gravity = android.view.Gravity.CENTER } })
                        if (!isPlaying) {
                            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                Text(if (!usbFound) "等待 USB 连接..." else if (!vpnRunning) "启动 VPN 隧道"
                                    else "输入 RTSP 地址并点击播放", fontSize = 14.sp, color = Color(0xFF475569))
                            }
                        }
                    }
                }

                // 展开/折叠按钮（视频区左上角）
                if (!sidebarExpanded) {
                    TextButton(onClick = { sidebarExpanded = true },
                        modifier = Modifier.padding(4.dp).size(36.dp).align(Alignment.TopStart),
                        contentPadding = PaddingValues(0.dp)
                    ) { Text("☰", fontSize = 18.sp, color = Color(0xFF38BDF8)) }
                } else {
                    TextButton(onClick = { sidebarExpanded = false },
                        modifier = Modifier.padding(4.dp).size(36.dp).align(Alignment.TopStart),
                        contentPadding = PaddingValues(0.dp)
                    ) { Text("✕", fontSize = 14.sp, color = Color(0xFF94A3B8)) }
                }
            }
        }
    }
}
