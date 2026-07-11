/**
 * MainActivity.kt — VPN 控制 + RTSP 播放器
 * 横屏优化：左侧控制栏 + 右侧全屏视频
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
import android.os.ResultReceiver
import android.util.Log
import android.view.SurfaceHolder
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
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.PowerSettingsNew
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material.icons.filled.Usb
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
                    Thread.sleep(1500)
                    usbDevice = findUsbDevice()
                    if (usbDevice != null) startAuthFlow()
                }
            )
        }

        if (usbDevice != null) startAuthFlow()
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
// 横屏主界面：可收起侧栏 + 全屏视频
// ═══════════════════════════════════════════════════════

@Composable
fun TunNatHubApp(usbFound: Boolean, vpnRunning: Boolean, connectionState: String = "idle", usbPollCount: Int = 0, onVpnTap: () -> Unit, onReconnect: (() -> Unit)? = null) {
    val ctx = LocalContext.current
    val prefs = ctx.getSharedPreferences("tun_nat_hub", Context.MODE_PRIVATE)

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
    var sidebarExpanded by remember { mutableStateOf(true) }

    // ── 录制 ──
    var isRecording by remember { mutableStateOf(false) }
    val RECORD_PATH = "${ctx.externalCacheDir?.absolutePath}/test_record.mp4"
    var recordPath by remember { mutableStateOf(RECORD_PATH) }

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
    var fwdExtPort by remember { mutableStateOf("") }   // RK3588 外网端口 (PC发包到这里)
    var fwdDestPort by remember { mutableStateOf("") }  // DJI RC 目标端口
    var fwdDestIp by remember { mutableStateOf("10.0.0.2") }
    var fwdMsg by remember { mutableStateOf("") }       // 校验/错误提示

    // ── LAN 网段 (预读 SharedPrefs, 给 config poller + 高级设置共用) ──
    val savedLanSubnet = prefs.getString("lan_subnet", "192.168.88.0") ?: "192.168.88.0"
    val savedLanPrefix = prefs.getInt("lan_prefix", 24)
    var needVpnReconnect by remember { mutableStateOf(false) }

    // ── 恢复已保存的解码器选择 ──
    val savedCodec = remember { prefs.getString("forced_codec", "auto") ?: "auto" }
    LaunchedEffect(Unit) {
        EasyPlayerClient.setForcedCodec(savedCodec)
    }

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
            } catch (e: Exception) {
                android.util.Log.e("TunNatHub", "API POST $path 失败: ${e.javaClass.simpleName} ${e.message}")
            }
        }
    }

    // ── 心跳轮询 (仅通过USB隧道 10.0.0.1:8080) ──
    LaunchedEffect(vpnRunning) {
        if (!vpnRunning) { android.util.Log.d("TunNatHub","心跳: VPN 关闭, 停止轮询"); hbCount = 0; return@LaunchedEffect }
        android.util.Log.d("TunNatHub", "心跳: 开始轮询 10.0.0.1:8080/api/heartbeat")
        while (vpnRunning) {
            kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
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
                    android.util.Log.d("TunNatHub", "心跳 OK #$hbCount bw=$hbBw tx=$hbTx rx=$hbRx")
                } catch (e: Exception) {
                    android.util.Log.e("TunNatHub", "心跳失败: ${e.javaClass.simpleName} ${e.message}")
                    hbDaemon = false; hbTty = false; hbTun = false
                }
            }
            kotlinx.coroutines.delay(1000)
        }
    }

    // ── 加载摄像头列表 + 端口转发 + LAN 网段同步 ──
    LaunchedEffect(vpnRunning) {
        if (!vpnRunning) return@LaunchedEffect
        kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.IO) {
            try {
                val url = java.net.URL("http://10.0.0.1:8080/api/config")
                val conn = url.openConnection() as java.net.HttpURLConnection
                conn.connectTimeout = 2000
                conn.readTimeout = 2000
                val text = conn.inputStream.bufferedReader().readText()
                AppLog.d("TunNatHub", "获取 V3s 配置: OK (${text.length} bytes)")
                // Parse cameras
                val camList = mutableListOf<CamInfo>()
                val camPattern = Regex("\"name\": \"([^\"]+)\"[^}]*\"url\": \"([^\"]+)\"")
                camPattern.findAll(text).forEach { m ->
                    camList.add(CamInfo(m.groupValues[1], m.groupValues[2]))
                }
                if (camList.isNotEmpty()) { cameras = camList; if (rtspUrl.isEmpty()) rtspUrl = camList[0].url }
                // Parse port forwards
                val fwdList = mutableListOf<FwdInfo>()
                val fwdPattern = Regex("\"proto\": \"(\\w+)\"[^}]*\"port\": (\\d+)[^}]*\"dest\": \"([^\"]+)\"")
                fwdPattern.findAll(text).forEach { m ->
                    fwdList.add(FwdInfo(m.groupValues[1], m.groupValues[2].toInt(), m.groupValues[3]))
                }
                forwards = fwdList
                // LAN 网段同步: web_panel 改过→App 自动同步→提示重连
                val lanMatch = Regex("\"lan_subnet\": \"(\\d+\\.\\d+\\.\\d+)\\.0/(\\d+)\"").find(text)
                if (lanMatch != null) {
                    val remoteSubnet = "${lanMatch.groupValues[1]}.0"
                    val remotePrefix = lanMatch.groupValues[2].toInt()
                    AppLog.d("TunNatHub", "V3s LAN网段: $remoteSubnet/$remotePrefix (App: $savedLanSubnet/$savedLanPrefix)")
                    if (remoteSubnet != savedLanSubnet || remotePrefix != savedLanPrefix) {
                        prefs.edit().putString("lan_subnet", remoteSubnet).putInt("lan_prefix", remotePrefix).apply()
                        needVpnReconnect = true
                        AppLog.w("TunNatHub", "网段不同步! V3s=$remoteSubnet/$remotePrefix App=$savedLanSubnet/$savedLanPrefix → 自动同步")
                    }
                }
            } catch (e: Exception) {
                android.util.Log.e("TunNatHub", "配置加载失败: ${e.javaClass.simpleName} ${e.message}")
            }
        }
    }

    val receiver = remember {
        object : ResultReceiver(Handler(ctx.mainLooper)) {
            override fun onReceiveResult(code: Int, data: Bundle?) {
                when (code) {
                    EasyPlayerClient.RESULT_VIDEO_DISPLAYED -> {
                        val decodeType = data?.getInt(EasyPlayerClient.KEY_VIDEO_DECODE_TYPE, -1) ?: -1
                        val codecName = EasyPlayerClient.getForcedCodec()
                        val typeStr = when {
                            codecName != "auto" -> codecName.split(".").last().take(25)
                            decodeType == 1 -> "MediaCodec(自动)"
                            decodeType == 0 -> "SW(FFmpeg)"
                            else -> "?"
                        }
                        statusText = "播放中 [$typeStr]"
                        isPlaying = true
                        AppLog.i("Player", "解码器: $typeStr")
                    }
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

    fun doStopRecord() {
        playerRef?.stopRecord()
        isRecording = false
    }

    // ── 从 RTSP URL 提取 IP 网段，自动同步 LAN 配置 ──
    fun autoSyncSubnet(url: String) {
        // 匹配 rtsp://x.x.x.x:port/path 中的 IP
        val ipMatch = Regex("rtsp://(\\d+\\.\\d+\\.\\d+)\\.\\d+").find(url) ?: return
        val base = ipMatch.groupValues[1]  // e.g. "192.168.144"
        val newSubnet = "$base.0"
        val currentSubnet = prefs.getString("lan_subnet", "192.168.88.0") ?: "192.168.88.0"
        if (newSubnet != currentSubnet) {
            prefs.edit().putString("lan_subnet", newSubnet).putInt("lan_prefix", 24).apply()
            needVpnReconnect = true
            AppLog.w("TunNatHub", "网段自动同步: $currentSubnet → $newSubnet (从 RTSP 地址推断)")
        }
    }

    fun togglePlay() {
        if (isPlaying) {
            if (isRecording) doStopRecord()
            playerRef?.stop(); playerRef = null; isPlaying = false; statusText = "已停止"
        } else {
            val sv = surfaceViewRef ?: return
            try {
                prefs.edit().putString("rtsp_url", rtspUrl).apply()
                // 自动同步 LAN 网段
                autoSyncSubnet(rtspUrl)
                val client = EasyPlayerClient(ctx, sv.holder.surface, receiver)
                client.start(rtspUrl, org.easydarwin.video.Client.TRANSTYPE_TCP, 1,
                    org.easydarwin.video.Client.EASY_SDK_VIDEO_FRAME_FLAG or
                    org.easydarwin.video.Client.EASY_SDK_AUDIO_FRAME_FLAG, "", "", null)
                playerRef = client; isPlaying = true; statusText = "连接中..."
            } catch (e: Exception) { Log.e("TunNatHub", "播放失败", e); statusText = "播放失败" }
        }
    }

    fun toggleRecord() {
        val client = playerRef ?: return
        if (isRecording) {
            client.stopRecord()
            isRecording = false
            statusText = "录制完成: $RECORD_PATH"
            AppLog.i("Record", "录制完成: $RECORD_PATH")
        } else {
            java.io.File(RECORD_PATH).parentFile?.mkdirs()
            java.io.File(RECORD_PATH).delete()  // 删除旧文件
            client.startRecord(RECORD_PATH)
            isRecording = true
            statusText = "录制中..."
            AppLog.i("Record", "开始录制: $RECORD_PATH")
        }
    }

    fun playLocalFile() {
        val file = java.io.File(RECORD_PATH)
        if (!file.exists()) { statusText = "无录制文件"; return }
        val intent = Intent(Intent.ACTION_VIEW).apply {
            setDataAndType(androidx.core.content.FileProvider.getUriForFile(ctx, "${ctx.packageName}.fileprovider", file), "video/*")
            addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK)
        }
        try {
            ctx.startActivity(intent)
            statusText = "本地回放中..."
        } catch (e: Exception) { statusText = "无可用播放器"; Log.e("TunNatHub", "本地回放失败", e) }
    }

    // 延迟测试状态 (提升到顶层，避免滚动时丢失)
    var latencyText by remember { mutableStateOf("") }
    var testing by remember { mutableStateOf(false) }

    MaterialTheme(colorScheme = darkColorScheme(
        background = Color(0xFF0F172A), surface = Color(0xFF1E293B), primary = Color(0xFF38BDF8),
        onBackground = Color(0xFFE2E8F0), onSurface = Color(0xFFE2E8F0), surfaceVariant = Color(0xFF1E293B)
    )) {
        Row(modifier = Modifier.fillMaxSize().background(Color(0xFF0F172A))) {

            // ═══ 侧边栏：320dp，上下固定 + 中间可滚动 ═══
            if (sidebarExpanded) {
                Surface(modifier = Modifier.width(320.dp).fillMaxHeight(),
                    color = Color(0xFF111827), shadowElevation = 8.dp
                ) {
                    Column(modifier = Modifier.fillMaxHeight()) {
                        // ── 顶部固定区：标题 + 关键状态（始终可见） ──
                        Surface(modifier = Modifier.fillMaxWidth(), color = Color(0xFF0F172A),
                            shadowElevation = 4.dp
                        ) {
                            Column(modifier = Modifier.padding(14.dp)) {
                                // 标题行
                                Row(modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceBetween,
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Text("TUN NAT HUB", fontSize = 18.sp, fontWeight = FontWeight.Bold,
                                        color = Color(0xFF38BDF8))
                                    TextButton(onClick = { sidebarExpanded = false },
                                        modifier = Modifier.size(28.dp), contentPadding = PaddingValues(0.dp)
                                    ) { Text("◀", fontSize = 12.sp, color = Color(0xFF94A3B8)) }
                                }

                                Spacer(Modifier.height(8.dp))

                                // USB + VPN 状态 (紧凑一行)
                                Row(modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceBetween,
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Row(verticalAlignment = Alignment.CenterVertically) {
                                        Surface(modifier = Modifier.size(7.dp),
                                            shape = androidx.compose.foundation.shape.CircleShape,
                                            color = if (usbFound) Color(0xFF22C55E) else Color(0xFFEF4444)) {}
                                        Spacer(Modifier.width(5.dp))
                                        Text(if (usbFound) "USB" else "无USB", fontSize = 11.sp,
                                            color = if (usbFound) Color(0xFF22C55E) else Color(0xFF94A3B8))
                                    }
                                    Row(verticalAlignment = Alignment.CenterVertically) {
                                        Surface(modifier = Modifier.size(7.dp),
                                            shape = androidx.compose.foundation.shape.CircleShape,
                                            color = if (vpnRunning) Color(0xFF22C55E) else Color(0xFFEF4444)) {}
                                        Spacer(Modifier.width(5.dp))
                                        Text(if (vpnRunning) "VPN" else "无VPN", fontSize = 11.sp,
                                            color = if (vpnRunning) Color(0xFF22C55E) else Color(0xFF94A3B8))
                                    }
                                    Button(onClick = onVpnTap, enabled = usbFound,
                                        modifier = Modifier.height(28.dp),
                                        contentPadding = PaddingValues(horizontal = 12.dp, vertical = 0.dp),
                                        colors = ButtonDefaults.buttonColors(
                                            containerColor = if (vpnRunning) Color(0xFFDC2626) else Color(0xFF2563EB))
                                    ) { Text(if (vpnRunning) "断开" else "连接", fontSize = 11.sp) }
                                }

                                Spacer(Modifier.height(6.dp))

                                // ── 心跳状态 (紧凑单行) ──
                                if (vpnRunning && hbCount > 0) {
                                    Row(modifier = Modifier.fillMaxWidth(),
                                        horizontalArrangement = Arrangement.SpaceBetween,
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Row(verticalAlignment = Alignment.CenterVertically) {
                                            Surface(modifier = Modifier.size(5.dp),
                                                shape = androidx.compose.foundation.shape.CircleShape,
                                                color = if (hbDaemon) Color(0xFF22C55E) else Color(0xFFEF4444)) {}
                                            Spacer(Modifier.width(2.dp))
                                            Surface(modifier = Modifier.size(5.dp),
                                                shape = androidx.compose.foundation.shape.CircleShape,
                                                color = if (hbTty) Color(0xFF22C55E) else Color(0xFFEF4444)) {}
                                            Spacer(Modifier.width(2.dp))
                                            Surface(modifier = Modifier.size(5.dp),
                                                shape = androidx.compose.foundation.shape.CircleShape,
                                                color = if (hbTun) Color(0xFF22C55E) else Color(0xFFEF4444)) {}
                                            Spacer(Modifier.width(6.dp))
                                            Text("${hbBw} Mbps", fontSize = 11.sp, fontWeight = FontWeight.Medium,
                                                color = Color(0xFF38BDF8))
                                        }
                                        Text("Tx${fmtSize(hbTx)} Rx${fmtSize(hbRx)}",
                                            fontSize = 9.sp, color = Color(0xFF64748B))
                                    }
                                } else if (vpnRunning) {
                                    Text("⏳ 链路建立中...", fontSize = 11.sp, color = Color(0xFFF59E0B))
                                } else if (connectionState == "scanning" && usbPollCount > 0) {
                                    Text("🔍 正在搜索设备 (${usbPollCount}s)...", fontSize = 11.sp, color = Color(0xFFF59E0B))
                                } else if (connectionState == "scanning") {
                                    Text("🔍 正在搜索设备...", fontSize = 11.sp, color = Color(0xFFF59E0B))
                                } else if (connectionState == "timeout") {
                                    Text("⚠ 未找到设备，请确认 USB 线已连接", fontSize = 11.sp, color = Color(0xFFF87171))
                                } else if (connectionState == "found") {
                                    Text("✅ 设备已发现，点击连接", fontSize = 11.sp, color = Color(0xFF22C55E))
                                } else {
                                    Text("请插入 USB 线连接设备", fontSize = 11.sp, color = Color(0xFF475569))
                                }
                                // ── 网段变化提示 (web_panel 改过 → App 需重连) ──
                                if (needVpnReconnect) {
                                    Spacer(Modifier.height(6.dp))
                                    Row(modifier = Modifier.fillMaxWidth().background(Color(0x33F59E0B), RoundedCornerShape(6.dp)).padding(8.dp),
                                        horizontalArrangement = Arrangement.SpaceBetween,
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Text("⚡ 网段已变更: $savedLanSubnet/$savedLanPrefix", fontSize = 10.sp, color = Color(0xFFFBBF24))
                                        Button(onClick = {
                                            needVpnReconnect = false
                                            if (vpnRunning) onVpnTap()  // 先断开
                                            onReconnect?.let { Thread { Thread.sleep(1500); android.os.Handler(android.os.Looper.getMainLooper()).post(it) }.start() }
                                        }, modifier = Modifier.height(24.dp),
                                            contentPadding = PaddingValues(horizontal = 8.dp, vertical = 0.dp),
                                            colors = ButtonDefaults.buttonColors(containerColor = Color(0xFFF59E0B))
                                        ) { Text("重连", fontSize = 10.sp, color = Color.Black) }
                                    }
                                }
                            }
                        }

                        // ── Debug 日志面板 (可折叠) ──
                        var debugExpanded by remember { mutableStateOf(false) }
                        val debugLogs by AppLog.logs.collectAsState()
                        val scrollState2 = rememberScrollState()

                        // 自动滚到最底
                        LaunchedEffect(debugLogs.size) { if (debugExpanded) scrollState2.animateScrollTo(Int.MAX_VALUE) }

                        Row(modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 2.dp)
                            .clickable { debugExpanded = !debugExpanded },
                            horizontalArrangement = Arrangement.SpaceBetween,
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Text("🐛 Debug", fontSize = 10.sp, color = Color(0xFF64748B))
                                Spacer(Modifier.width(4.dp))
                                Text("(${debugLogs.size})", fontSize = 9.sp, color = Color(0xFF475569))
                            }
                            Row { Text(if (debugExpanded) "▲" else "▼", fontSize = 9.sp, color = Color(0xFF475569)) }
                        }

                        if (debugExpanded) {
                            Box(modifier = Modifier.fillMaxWidth().heightIn(max = 180.dp).padding(horizontal = 14.dp)
                                .background(Color(0xFF020617), RoundedCornerShape(6.dp))
                                .border(1.dp, Color(0xFF1E293B), RoundedCornerShape(6.dp))
                            ) {
                                Column(modifier = Modifier.verticalScroll(scrollState2).padding(6.dp)) {
                                    val recent = debugLogs.takeLast(50).reversed()
                                    if (recent.isEmpty()) {
                                        Text("等待日志...", fontSize = 9.sp, color = Color(0xFF475569))
                                    }
                                    recent.forEach { entry ->
                                        val color = when (entry.level) {
                                            AppLog.Level.ERROR -> Color(0xFFEF4444)
                                            AppLog.Level.WARN -> Color(0xFFF59E0B)
                                            AppLog.Level.INFO -> Color(0xFF38BDF8)
                                            AppLog.Level.DEBUG -> Color(0xFF64748B)
                                        }
                                        Text(
                                            text = entry.fullLine,
                                            fontSize = 9.sp,
                                            color = color,
                                            lineHeight = 13.sp,
                                            modifier = Modifier.padding(vertical = 1.dp)
                                        )
                                    }
                                }
                            }
                            Spacer(Modifier.height(2.dp))
                            // Clear button
                            TextButton(onClick = { AppLog.clear() },
                                modifier = Modifier.height(22.dp).padding(horizontal = 14.dp),
                                contentPadding = PaddingValues(horizontal = 6.dp, vertical = 0.dp)
                            ) { Text("清空", fontSize = 9.sp, color = Color(0xFF64748B)) }
                        }

                        HorizontalDivider(color = Color(0xFF1E293B))

                        // ── 中间可滚动区 ──
                        val scrollState = rememberScrollState()
                        Column(modifier = Modifier.weight(1f).verticalScroll(scrollState).padding(14.dp),
                            verticalArrangement = Arrangement.Top
                        ) {
                            // 播放区域
                            Text("RTSP 地址", fontSize = 11.sp, color = Color(0xFF94A3B8),
                                modifier = Modifier.padding(bottom = 4.dp))
                            Box(modifier = Modifier
                                .fillMaxWidth().height(44.dp)
                                .background(Color(0xFF0F172A), RoundedCornerShape(8.dp))
                                .border(1.dp, Color(0xFF334155), RoundedCornerShape(8.dp))
                                .padding(horizontal = 12.dp),
                                contentAlignment = Alignment.CenterStart
                            ) {
                                if (rtspUrl.isEmpty()) {
                                    Text("rtsp://192.168.88.100:554/stream1", fontSize = 14.sp,
                                        color = Color(0xFF475569))
                                }
                                BasicTextField(
                                    value = rtspUrl, onValueChange = { rtspUrl = it },
                                    singleLine = true,
                                    textStyle = androidx.compose.ui.text.TextStyle(
                                        fontSize = 14.sp, color = Color(0xFFE2E8F0)),
                                    cursorBrush = androidx.compose.ui.graphics.SolidColor(Color(0xFF38BDF8)),
                                    keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Uri,
                                        imeAction = ImeAction.Done),
                                    modifier = Modifier.fillMaxWidth()
                                )
                            }

                            Spacer(Modifier.height(6.dp))

                            // 播放按钮 + 状态
                            Button(onClick = { togglePlay() },
                                modifier = Modifier.fillMaxWidth().height(36.dp),
                                colors = ButtonDefaults.buttonColors(
                                    containerColor = if (isPlaying) Color(0xFFDC2626) else Color(0xFF16A34A))
                            ) { Text(if (isPlaying) "■ 停止" else "▶ 播放", fontSize = 13.sp,
                                fontWeight = FontWeight.Medium) }

                            // ── 录制按钮行 ──
                            if (isPlaying) {
                                Spacer(Modifier.height(4.dp))
                                Row(modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.spacedBy(6.dp)
                                ) {
                                    Button(onClick = { toggleRecord() },
                                        modifier = Modifier.weight(1f).height(28.dp),
                                        contentPadding = PaddingValues(horizontal = 8.dp, vertical = 0.dp),
                                        colors = ButtonDefaults.buttonColors(
                                            containerColor = if (isRecording) Color(0xFFDC2626) else Color(0xFF7C3AED))
                                    ) { Text(if (isRecording) "⏹ 停止录制" else "⏺ 录制", fontSize = 10.sp) }
                                    Button(onClick = { playLocalFile() },
                                        modifier = Modifier.weight(1f).height(28.dp),
                                        contentPadding = PaddingValues(horizontal = 8.dp, vertical = 0.dp),
                                        colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF0EA5E9))
                                    ) { Text("📁 本地回放", fontSize = 10.sp) }
                                }
                            }

                            if (statusText.isNotEmpty()) {
                                Spacer(Modifier.height(4.dp))
                                Text(statusText, fontSize = 11.sp,
                                    color = if (isPlaying) Color(0xFF22C55E) else Color(0xFF94A3B8))
                            }
                            if (resolutionText.isNotEmpty())
                                Text(resolutionText, fontSize = 10.sp, color = Color(0xFF64748B))

                            Spacer(Modifier.height(8.dp))

                            // ── 延迟测试 ──
                            Row(modifier = Modifier.fillMaxWidth(),
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
                                                    latencyText = "%.1f/%.1f/%.1f ms (丢$drops)".format(avg, p50, p95)
                                                } else { latencyText = "全部丢包 ($drops/10)" }
                                            } catch (e: Exception) { latencyText = "失败" }
                                            testing = false
                                        }.start()
                                    }
                                }, enabled = vpnRunning && !testing, modifier = Modifier.height(28.dp),
                                    contentPadding = PaddingValues(horizontal = 8.dp, vertical = 0.dp),
                                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF334155))
                                ) { Text(if (testing) "⏳" else "⏱", fontSize = 11.sp) }
                            }
                            if (latencyText.isNotEmpty())
                                Text(latencyText, fontSize = 9.sp, color = Color(0xFF38BDF8),
                                    modifier = Modifier.padding(top = 2.dp))

                            Spacer(Modifier.height(8.dp))
                            HorizontalDivider(color = Color(0xFF1E293B))
                            Spacer(Modifier.height(6.dp))

                            // ── 端口转发 ──
                            Text("🔀 端口转发", fontSize = 11.sp, color = Color(0xFF94A3B8))
                            Text("PC → 192.168.88.66:外网端口 ─DNAT─→ DJI:目标端口", fontSize = 9.sp,
                                color = Color(0xFF475569), modifier = Modifier.padding(top = 2.dp))
                            Spacer(Modifier.height(8.dp))

                            // 行1: 协议 + 外网端口
                            Row(modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.spacedBy(8.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                // 协议按钮
                                Surface(
                                    modifier = Modifier.height(44.dp).widthIn(min = 52.dp),
                                    color = Color(0xFF1E293B), shape = RoundedCornerShape(8.dp),
                                    onClick = { fwdProto = if (fwdProto == "udp") "tcp" else "udp" }
                                ) {
                                    Box(contentAlignment = Alignment.Center,
                                        modifier = Modifier.fillMaxSize()) {
                                        Text(fwdProto.uppercase(), fontSize = 14.sp,
                                            fontWeight = FontWeight.Medium,
                                            color = Color(0xFF38BDF8))
                                    }
                                }
                                // 外网端口 (RK3588 end1 上暴露的端口)
                                Column(modifier = Modifier.weight(1f)) {
                                    Text("外网端口", fontSize = 10.sp, color = Color(0xFF64748B),
                                        modifier = Modifier.padding(bottom = 2.dp))
                                    Box(modifier = Modifier
                                        .fillMaxWidth().height(44.dp)
                                        .background(Color(0xFF0F172A), RoundedCornerShape(8.dp))
                                        .border(1.dp, Color(0xFF475569), RoundedCornerShape(8.dp))
                                        .padding(horizontal = 12.dp),
                                        contentAlignment = Alignment.CenterStart
                                    ) {
                                        if (fwdExtPort.isEmpty()) {
                                            Text("PC发包端口 如5566", fontSize = 15.sp,
                                                color = Color(0xFF475569))
                                        }
                                        BasicTextField(
                                            value = fwdExtPort,
                                            onValueChange = { fwdExtPort = it },
                                            singleLine = true,
                                            textStyle = androidx.compose.ui.text.TextStyle(
                                                fontSize = 15.sp, color = Color.White),
                                            cursorBrush = androidx.compose.ui.graphics.SolidColor(Color.White),
                                            keyboardOptions = KeyboardOptions(
                                                keyboardType = KeyboardType.Number),
                                            modifier = Modifier.fillMaxWidth()
                                        )
                                    }
                                }
                            }

                            Spacer(Modifier.height(8.dp))

                            // 行2: 目标IP + 目标端口
                            Row(modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.spacedBy(8.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                // 目标IP
                                Column(modifier = Modifier.weight(1f)) {
                                    Text("DJI IP", fontSize = 10.sp, color = Color(0xFF64748B),
                                        modifier = Modifier.padding(bottom = 2.dp))
                                    Box(modifier = Modifier
                                        .fillMaxWidth().height(44.dp)
                                        .background(Color(0xFF0F172A), RoundedCornerShape(8.dp))
                                        .border(1.dp, Color(0xFF475569), RoundedCornerShape(8.dp))
                                        .padding(horizontal = 12.dp),
                                        contentAlignment = Alignment.CenterStart
                                    ) {
                                        if (fwdDestIp.isEmpty()) {
                                            Text("10.0.0.2", fontSize = 15.sp,
                                                color = Color(0xFF475569))
                                        }
                                        BasicTextField(
                                            value = fwdDestIp,
                                            onValueChange = { fwdDestIp = it },
                                            singleLine = true,
                                            textStyle = androidx.compose.ui.text.TextStyle(
                                                fontSize = 15.sp, color = Color.White),
                                            cursorBrush = androidx.compose.ui.graphics.SolidColor(Color.White),
                                            modifier = Modifier.fillMaxWidth()
                                        )
                                    }
                                }
                                // 目标端口
                                Column(modifier = Modifier.width(80.dp)) {
                                    Text("目标端口", fontSize = 10.sp, color = Color(0xFF64748B),
                                        modifier = Modifier.padding(bottom = 2.dp))
                                    Box(modifier = Modifier
                                        .fillMaxWidth().height(44.dp)
                                        .background(Color(0xFF0F172A), RoundedCornerShape(8.dp))
                                        .border(1.dp, Color(0xFF475569), RoundedCornerShape(8.dp))
                                        .padding(horizontal = 12.dp),
                                        contentAlignment = Alignment.CenterStart
                                    ) {
                                        if (fwdDestPort.isEmpty()) {
                                            Text("如5566", fontSize = 15.sp,
                                                color = Color(0xFF475569))
                                        }
                                        BasicTextField(
                                            value = fwdDestPort,
                                            onValueChange = { fwdDestPort = it },
                                            singleLine = true,
                                            textStyle = androidx.compose.ui.text.TextStyle(
                                                fontSize = 15.sp, color = Color.White),
                                            cursorBrush = androidx.compose.ui.graphics.SolidColor(Color.White),
                                            keyboardOptions = KeyboardOptions(
                                                keyboardType = KeyboardType.Number),
                                            modifier = Modifier.fillMaxWidth()
                                        )
                                    }
                                }
                            }

                            Spacer(Modifier.height(8.dp))

                            // 错误提示
                            if (fwdMsg.isNotEmpty()) {
                                Text(fwdMsg, fontSize = 10.sp, color = Color(0xFFF87171),
                                    modifier = Modifier.padding(bottom = 4.dp))
                            }

                            // 添加按钮
                            Button(
                                onClick = {
                                    fwdMsg = ""
                                    val extPortStr = fwdExtPort
                                    val dstPortStr = fwdDestPort
                                    val dstIp = fwdDestIp.ifEmpty { "10.0.0.2" }
                                    val proto = fwdProto

                                    val extPort = extPortStr.toIntOrNull()
                                    val dstPort = dstPortStr.toIntOrNull()
                                    val ok = when {
                                        extPort == null || extPort < 1 || extPort > 65535 -> {
                                            fwdMsg = "请输入有效外网端口 (1-65535)"
                                            Log.w("TunNatHub", "转发失败: 外网端口='$extPortStr'")
                                            false
                                        }
                                        dstPort != null && (dstPort < 1 || dstPort > 65535) -> {
                                            fwdMsg = "目标端口无效 (1-65535)"
                                            false
                                        }
                                        else -> true
                                    }
                                    if (!ok) return@Button

                                    val ePort = extPort!!  // 已通过 when 校验
                                    val dest = if (dstPort != null) "$dstIp:$dstPort" else dstIp
                                    Log.d("TunNatHub", "添加转发: $proto ext=$ePort dest=$dest")
                                    fwdExtPort = ""
                                    fwdDestPort = ""
                                    forwards = forwards + FwdInfo(proto, ePort, dest)
                                    apiPost("/api/forward/add",
                                        """{"proto":"$proto","port":$ePort,"dest":"$dest"}""")
                                },
                                modifier = Modifier.fillMaxWidth().height(40.dp),
                                colors = ButtonDefaults.buttonColors(
                                    containerColor = Color(0xFF2563EB))
                            ) { Text("＋ 添加转发规则", fontSize = 13.sp) }

                            if (forwards.isEmpty()) {
                                Text("示例: UDP 外网端口5566 → 10.0.0.2:5566", fontSize = 9.sp,
                                    color = Color(0xFF475569),
                                    modifier = Modifier.padding(start = 2.dp, top = 6.dp))
                            } else {
                                Spacer(Modifier.height(6.dp))
                                forwards.forEach { f ->
                                    Row(modifier = Modifier.fillMaxWidth().padding(vertical = 2.dp),
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Text("${f.proto.uppercase()} :${f.port} → ${f.dest}",
                                            fontSize = 10.sp, color = Color(0xFF22C55E),
                                            modifier = Modifier.weight(1f))
                                        TextButton(onClick = {
                                            apiPost("/api/forward/del", """{"port":${f.port}}""")
                                            forwards = forwards.filter { it.port != f.port }
                                        }, modifier = Modifier.height(22.dp),
                                            contentPadding = PaddingValues(3.dp, 0.dp)
                                        ) { Text("✕", fontSize = 10.sp, color = Color(0xFFEF4444)) }
                                    }
                                }
                            }
                            // 提示外网端口与目标端口可不同
                            Text("💡 外网→目标端口可不同,如: 10000→10.0.0.2:80",
                                fontSize = 8.sp, color = Color(0xFF475569),
                                modifier = Modifier.padding(top = 4.dp))

                            // ── 摄像头列表 ──
                            if (cameras.isNotEmpty()) {
                                Spacer(Modifier.height(8.dp))
                                HorizontalDivider(color = Color(0xFF1E293B))
                                Spacer(Modifier.height(4.dp))
                                Text("📹 摄像头", fontSize = 10.sp, color = Color(0xFF94A3B8))
                                cameras.forEachIndexed { i, c ->
                                    Row(modifier = Modifier.fillMaxWidth().padding(vertical = 1.dp),
                                        verticalAlignment = Alignment.CenterVertically
                                    ) {
                                        Surface(modifier = Modifier.size(5.dp),
                                            shape = androidx.compose.foundation.shape.CircleShape,
                                            color = if (i == selectedCam) Color(0xFF38BDF8) else Color(0xFF334155)) {}
                                        Spacer(Modifier.width(4.dp))
                                        Text(c.name, fontSize = 9.sp,
                                            color = if (i == selectedCam) Color(0xFF38BDF8) else Color(0xFF64748B),
                                            modifier = Modifier.weight(1f))
                                        if (i != selectedCam) {
                                            TextButton(onClick = {
                                                selectedCam = i; rtspUrl = cameras[i].url
                                            }, modifier = Modifier.height(18.dp),
                                                contentPadding = PaddingValues(3.dp, 0.dp)
                                            ) { Text("切", fontSize = 8.sp, color = Color(0xFF38BDF8)) }
                                        }
                                    }
                                }
                            }

                            // ── 高级设置 (可折叠) ──
                            Spacer(Modifier.height(8.dp))
                            HorizontalDivider(color = Color(0xFF1E293B))
                            var advancedExpanded by remember { mutableStateOf(false) }
                            var lanSubnet by remember { mutableStateOf(savedLanSubnet) }
                            var lanPrefixStr by remember { mutableStateOf(savedLanPrefix.toString()) }
                            var advSaved by remember { mutableStateOf(false) }

                            Row(modifier = Modifier.fillMaxWidth().padding(top = 4.dp)
                                .clickable { advancedExpanded = !advancedExpanded },
                                horizontalArrangement = Arrangement.SpaceBetween,
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                Row(verticalAlignment = Alignment.CenterVertically) {
                                    Text("⚙ 高级", fontSize = 10.sp, color = Color(0xFF64748B))
                                    if (!advancedExpanded) {
                                        Spacer(Modifier.width(6.dp))
                                        Text("$savedLanSubnet/${savedLanPrefix}", fontSize = 9.sp, color = Color(0xFF475569))
                                    }
                                }
                                Text(if (advancedExpanded) "▲" else "▼", fontSize = 9.sp, color = Color(0xFF475569))
                            }

                            if (advancedExpanded) {
                                Spacer(Modifier.height(6.dp))
                                Text("LAN 网段 (路由到 USB 隧道)", fontSize = 9.sp, color = Color(0xFF64748B))
                                Text("修改后需断开并重连 VPN 生效", fontSize = 8.sp, color = Color(0xFF475569))
                                Spacer(Modifier.height(4.dp))
                                Row(modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Box(modifier = Modifier.weight(1f).height(36.dp)
                                        .background(Color(0xFF0F172A), RoundedCornerShape(6.dp))
                                        .border(1.dp, Color(0xFF334155), RoundedCornerShape(6.dp))
                                        .padding(horizontal = 10.dp),
                                        contentAlignment = Alignment.CenterStart
                                    ) {
                                        BasicTextField(value = lanSubnet, onValueChange = { lanSubnet = it; advSaved = false },
                                            singleLine = true,
                                            textStyle = androidx.compose.ui.text.TextStyle(fontSize = 13.sp, color = Color(0xFFE2E8F0)),
                                            cursorBrush = androidx.compose.ui.graphics.SolidColor(Color(0xFF38BDF8)),
                                            modifier = Modifier.fillMaxWidth())
                                    }
                                    Text("/", fontSize = 14.sp, color = Color(0xFF64748B))
                                    Box(modifier = Modifier.width(40.dp).height(36.dp)
                                        .background(Color(0xFF0F172A), RoundedCornerShape(6.dp))
                                        .border(1.dp, Color(0xFF334155), RoundedCornerShape(6.dp))
                                        .padding(horizontal = 10.dp),
                                        contentAlignment = Alignment.Center
                                    ) {
                                        BasicTextField(value = lanPrefixStr, onValueChange = { lanPrefixStr = it; advSaved = false },
                                            singleLine = true,
                                            textStyle = androidx.compose.ui.text.TextStyle(fontSize = 13.sp, color = Color(0xFFE2E8F0)),
                                            cursorBrush = androidx.compose.ui.graphics.SolidColor(Color(0xFF38BDF8)),
                                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                                            modifier = Modifier.fillMaxWidth())
                                    }
                                }
                                Spacer(Modifier.height(6.dp))
                                Row(modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.spacedBy(6.dp)
                                ) {
                                    Button(onClick = {
                                        val prefix = lanPrefixStr.toIntOrNull()
                                        if (prefix == null || prefix < 8 || prefix > 30) {
                                            lanPrefixStr = savedLanPrefix.toString()
                                            return@Button
                                        }
                                        prefs.edit().putString("lan_subnet", lanSubnet).putInt("lan_prefix", prefix).apply()
                                        advSaved = true
                                        // 同步到 V3s Web Panel (更新 config.json 中的 lan_subnet 显示)
                                        apiPost("/api/config/save",
                                            """{"lan_subnet":"${lanSubnet}/${prefix}"}""")
                                    }, modifier = Modifier.height(30.dp),
                                        contentPadding = PaddingValues(horizontal = 10.dp, vertical = 0.dp),
                                        colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF2563EB))
                                    ) { Text("保存", fontSize = 11.sp) }

                                    Button(onClick = {
                                        lanSubnet = "192.168.88.0"
                                        lanPrefixStr = "24"
                                        prefs.edit().putString("lan_subnet", "192.168.88.0").putInt("lan_prefix", 24).apply()
                                        advSaved = true
                                    }, modifier = Modifier.height(30.dp),
                                        contentPadding = PaddingValues(horizontal = 10.dp, vertical = 0.dp),
                                        colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF334155))
                                    ) { Text("默认", fontSize = 10.sp) }
                                }
                                // ── 解码器选择 ──
                                Spacer(Modifier.height(8.dp))
                                HorizontalDivider(color = Color(0xFF1E293B))
                                Spacer(Modifier.height(4.dp))
                                Text("解码器", fontSize = 9.sp, color = Color(0xFF64748B))

                                var selectedCodec by remember { mutableStateOf(EasyPlayerClient.getForcedCodec()) }
                                var codecList by remember { mutableStateOf(listOf("auto")) }
                                var codecDropdown by remember { mutableStateOf(false) }
                                var codecSaved by remember { mutableStateOf(false) }

                                // 加载可用解码器列表
                                LaunchedEffect(advancedExpanded) {
                                    if (advancedExpanded) {
                                        try {
                                            val list = EasyPlayerClient.listAvailableDecoders()
                                            codecList = listOf("auto") + list
                                        } catch (_: Exception) {}
                                    }
                                }

                                Row(modifier = Modifier.fillMaxWidth(),
                                    horizontalArrangement = Arrangement.SpaceBetween,
                                    verticalAlignment = Alignment.CenterVertically
                                ) {
                                    Box(modifier = Modifier.weight(1f)) {
                                        Row(modifier = Modifier.fillMaxWidth().height(32.dp)
                                            .background(Color(0xFF0F172A), RoundedCornerShape(6.dp))
                                            .border(1.dp, Color(0xFF334155), RoundedCornerShape(6.dp))
                                            .clickable { codecDropdown = !codecDropdown }
                                            .padding(horizontal = 10.dp),
                                            verticalAlignment = Alignment.CenterVertically
                                        ) {
                                            Text(
                                                text = selectedCodec.let {
                                                    if (it == "auto") "auto (自动)"
                                                    else if (it.contains("low_latency")) it + " ⚡"
                                                    else if (it.contains(".qti.")) it + " (HW)"
                                                    else if (it.contains("android")) it + " (SW)"
                                                    else it
                                                },
                                                fontSize = 10.sp,
                                                color = if (selectedCodec == "auto") Color(0xFF22C55E) else Color(0xFFF59E0B),
                                                maxLines = 1
                                            )
                                            Spacer(Modifier.weight(1f))
                                            Text(if (codecDropdown) "▲" else "▼", fontSize = 9.sp, color = Color(0xFF64748B))
                                        }
                                        DropdownMenu(expanded = codecDropdown, onDismissRequest = { codecDropdown = false },
                                            modifier = Modifier.background(Color(0xFF1E293B))
                                        ) {
                                            codecList.forEach { codec ->
                                                DropdownMenuItem(
                                                    text = {
                                                        Text(
                                                            text = codec.let {
                                                                if (it == "auto") "auto (自动)"
                                                                else if (it.contains("low_latency")) it + " ⚡"
                                                                else if (it.contains(".qti.")) it + " (HW)"
                                                                else if (it.contains("android")) it + " (SW)"
                                                                else it
                                                            },
                                                            fontSize = 10.sp,
                                                            color = Color(0xFFE2E8F0)
                                                        )
                                                    },
                                                    onClick = {
                                                        selectedCodec = codec
                                                        codecDropdown = false
                                                        codecSaved = false
                                                    },
                                                    modifier = Modifier.background(
                                                        if (codec == selectedCodec) Color(0xFF334155) else Color(0xFF1E293B)
                                                    )
                                                )
                                            }
                                        }
                                    }
                                    Spacer(Modifier.width(6.dp))
                                    Button(onClick = {
                                        EasyPlayerClient.setForcedCodec(selectedCodec)
                                        codecSaved = true
                                        // 保存在 SharedPrefs
                                        prefs.edit().putString("forced_codec", selectedCodec).apply()
                                    }, modifier = Modifier.height(30.dp),
                                        contentPadding = PaddingValues(horizontal = 8.dp, vertical = 0.dp),
                                        colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF2563EB))
                                    ) { Text("应用", fontSize = 10.sp) }
                                }
                                if (codecSaved) {
                                    Text("✅ 解码器已切换, 重启播放生效", fontSize = 9.sp,
                                        color = Color(0xFFF59E0B), modifier = Modifier.padding(top = 2.dp))
                                }

                                if (advSaved) {
                                    Text("✅ 已保存, 重连 VPN 生效", fontSize = 9.sp,
                                        color = Color(0xFF22C55E), modifier = Modifier.padding(top = 4.dp))
                                }
                            }
                        }

                        // ── 底部固定区：版本/设备信息 ──
                        HorizontalDivider(color = Color(0xFF1E293B))
                        Surface(modifier = Modifier.fillMaxWidth(), color = Color(0xFF0F172A)) {
                            Column(modifier = Modifier.padding(horizontal = 14.dp, vertical = 8.dp)) {
                                Text("Linux 192.168.88.66 · USB 隧道", fontSize = 9.sp, color = Color(0xFF475569))
                                Text("TUN 10.0.0.0/24 · VID 0x0BDA PID 0x8812", fontSize = 9.sp, color = Color(0xFF475569))
                                Text("v${BuildConfig.VERSION_NAME}", fontSize = 10.sp, color = Color(0xFF38BDF8))
                            }
                        }
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
                                FrameLayout.LayoutParams.MATCH_PARENT,
                                FrameLayout.LayoutParams.MATCH_PARENT
                            ).apply { gravity = android.view.Gravity.CENTER } })
                        if (!isPlaying) {
                            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                                Text(if (!usbFound) "等待 USB 连接..."
                                    else if (!vpnRunning) "启动 VPN 隧道"
                                    else "输入 RTSP 地址并点击播放",
                                    fontSize = 14.sp, color = Color(0xFF475569))
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
