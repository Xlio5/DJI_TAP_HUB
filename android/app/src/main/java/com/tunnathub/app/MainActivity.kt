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
import com.tunnathub.app.service.TunNatVpnService
import com.tunnathub.app.usb.UsbBridge
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
// 横屏主界面：左侧控制栏 + 右侧视频
// ═══════════════════════════════════════════════════════

@Composable
fun TunNatHubApp(usbFound: Boolean, vpnRunning: Boolean, onVpnTap: () -> Unit) {
    val ctx = LocalContext.current
    val prefs = ctx.getSharedPreferences("tun_nat_hub", Context.MODE_PRIVATE)

    // RTSP 播放状态
    val savedUrl = prefs.getString("rtsp_url", "rtsp://192.168.88.100:554/stream1")
        ?: "rtsp://192.168.88.100:554/stream1"
    var rtspUrl by remember { mutableStateOf(savedUrl) }
    var isPlaying by remember { mutableStateOf(false) }
    var statusText by remember { mutableStateOf("") }
    var resolutionText by remember { mutableStateOf("") }
    var surfaceViewRef by remember { mutableStateOf<SurfaceView?>(null) }
    var playerRef by remember { mutableStateOf<EasyPlayerClient?>(null) }

    // 播放器回调
    val receiver = remember {
        object : ResultReceiver(Handler(ctx.mainLooper)) {
            override fun onReceiveResult(code: Int, data: Bundle?) {
                when (code) {
                    EasyPlayerClient.RESULT_VIDEO_DISPLAYED -> {
                        statusText = "播放中"
                        isPlaying = true
                    }
                    EasyPlayerClient.RESULT_VIDEO_SIZE -> {
                        val w = data?.getInt(EasyPlayerClient.EXTRA_VIDEO_WIDTH, 0) ?: 0
                        val h = data?.getInt(EasyPlayerClient.EXTRA_VIDEO_HEIGHT, 0) ?: 0
                        resolutionText = "${w}x${h}"
                    }
                    EasyPlayerClient.RESULT_TIMEOUT -> {
                        statusText = "连接超时"
                        isPlaying = false
                    }
                    EasyPlayerClient.RESULT_EVENT -> {
                        val msg = data?.getString("event-msg")
                        if (msg != null) statusText = msg
                    }
                    EasyPlayerClient.RESULT_UNSUPPORTED_VIDEO -> {
                        statusText = "编码不支持"
                        isPlaying = false
                    }
                }
            }
        }
    }

    fun togglePlay() {
        if (isPlaying) {
            playerRef?.stop()
            playerRef = null
            isPlaying = false
            statusText = "已停止"
        } else {
            val sv = surfaceViewRef ?: return
            try {
                prefs.edit().putString("rtsp_url", rtspUrl).apply()
                val client = EasyPlayerClient(ctx, sv.holder.surface, receiver)
                client.start(
                    rtspUrl,
                    org.easydarwin.video.Client.TRANSTYPE_TCP,
                    50,
                    org.easydarwin.video.Client.EASY_SDK_VIDEO_FRAME_FLAG or
                    org.easydarwin.video.Client.EASY_SDK_AUDIO_FRAME_FLAG,
                    "", "", null
                )
                playerRef = client
                isPlaying = true
                statusText = "连接中..."
            } catch (e: Exception) {
                Log.e("TunNatHub", "播放失败", e)
                statusText = "播放失败"
            }
        }
    }

    // ═══ 布局 ═══
    MaterialTheme(
        colorScheme = darkColorScheme(
            background = Color(0xFF0F172A),
            surface = Color(0xFF1E293B),
            primary = Color(0xFF38BDF8),
            onBackground = Color(0xFFE2E8F0),
            onSurface = Color(0xFFE2E8F0),
            surfaceVariant = Color(0xFF1E293B)
        )
    ) {
        Row(modifier = Modifier.fillMaxSize().background(Color(0xFF0F172A))) {
            // ═══ 左侧控制面板 ═══
            Surface(
                modifier = Modifier.width(340.dp).fillMaxHeight(),
                color = Color(0xFF111827),
                shadowElevation = 8.dp
            ) {
                Column(
                    modifier = Modifier.fillMaxHeight().padding(16.dp),
                    verticalArrangement = Arrangement.Top
                ) {
                    // 标题
                    Text(
                        "TUN NAT HUB",
                        fontSize = 20.sp,
                        fontWeight = FontWeight.Bold,
                        color = Color(0xFF38BDF8),
                        modifier = Modifier.padding(bottom = 4.dp)
                    )
                    Text(
                        "USB 隧道 · 视频传输",
                        fontSize = 11.sp,
                        color = Color(0xFF64748B),
                        modifier = Modifier.padding(bottom = 16.dp)
                    )

                    // ── USB 状态 ──
                    Row(
                        modifier = Modifier.padding(bottom = 8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Surface(
                            modifier = Modifier.size(8.dp),
                            shape = androidx.compose.foundation.shape.CircleShape,
                            color = if (usbFound) Color(0xFF22C55E) else Color(0xFFEF4444)
                        ) {}
                        Spacer(Modifier.width(8.dp))
                        Text(
                            if (usbFound) "USB 已检测" else "USB 未连接",
                            fontSize = 13.sp,
                            color = if (usbFound) Color(0xFF22C55E) else Color(0xFF94A3B8)
                        )
                    }

                    // ── VPN 状态 + 按钮 ──
                    Row(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(bottom = 12.dp),
                        verticalAlignment = Alignment.CenterVertically,
                        horizontalArrangement = Arrangement.SpaceBetween
                    ) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Surface(
                                modifier = Modifier.size(8.dp),
                                shape = androidx.compose.foundation.shape.CircleShape,
                                color = if (vpnRunning) Color(0xFF22C55E) else Color(0xFFEF4444)
                            ) {}
                            Spacer(Modifier.width(8.dp))
                            Text(
                                if (vpnRunning) "VPN 已连接" else "VPN 未连接",
                                fontSize = 13.sp,
                                color = if (vpnRunning) Color(0xFF22C55E) else Color(0xFF94A3B8)
                            )
                        }
                        Button(
                            onClick = onVpnTap,
                            enabled = usbFound,
                            modifier = Modifier.height(34.dp),
                            contentPadding = PaddingValues(horizontal = 16.dp, vertical = 2.dp),
                            colors = ButtonDefaults.buttonColors(
                                containerColor = if (vpnRunning) Color(0xFFDC2626) else Color(0xFF2563EB)
                            )
                        ) {
                            Text(
                                if (vpnRunning) "断开" else "连接",
                                fontSize = 13.sp
                            )
                        }
                    }

                    HorizontalDivider(color = Color(0xFF1E293B), modifier = Modifier.padding(vertical = 4.dp))

                    // ── RTSP 地址 ──
                    Text(
                        "RTSP 摄像头地址",
                        fontSize = 12.sp,
                        color = Color(0xFF94A3B8),
                        modifier = Modifier.padding(top = 8.dp, bottom = 4.dp)
                    )
                    OutlinedTextField(
                        value = rtspUrl,
                        onValueChange = { rtspUrl = it },
                        modifier = Modifier.fillMaxWidth(),
                        singleLine = true,
                        textStyle = LocalTextStyle.current.copy(
                            fontSize = 13.sp,
                            color = Color(0xFFE2E8F0)
                        ),
                        colors = OutlinedTextFieldDefaults.colors(
                            focusedBorderColor = Color(0xFF38BDF8),
                            unfocusedBorderColor = Color(0xFF334155),
                            cursorColor = Color(0xFF38BDF8)
                        ),
                        keyboardOptions = KeyboardOptions(
                            keyboardType = KeyboardType.Uri,
                            imeAction = ImeAction.Done
                        )
                    )

                    Spacer(Modifier.height(8.dp))

                    // ── 播放/停止按钮 ──
                    Button(
                        onClick = { togglePlay() },
                        modifier = Modifier.fillMaxWidth().height(40.dp),
                        colors = ButtonDefaults.buttonColors(
                            containerColor = if (isPlaying) Color(0xFFDC2626) else Color(0xFF16A34A)
                        )
                    ) {
                        Text(
                            if (isPlaying) "■ 停止播放" else "▶ 开始播放",
                            fontSize = 14.sp,
                            fontWeight = FontWeight.Medium
                        )
                    }

                    Spacer(Modifier.height(10.dp))

                    // ── 播放状态 ──
                    if (statusText.isNotEmpty()) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            if (isPlaying) {
                                Surface(
                                    modifier = Modifier.size(6.dp),
                                    shape = androidx.compose.foundation.shape.CircleShape,
                                    color = Color(0xFF22C55E)
                                ) {}
                                Spacer(Modifier.width(6.dp))
                            }
                            Text(
                                statusText,
                                fontSize = 12.sp,
                                color = if (isPlaying) Color(0xFF22C55E) else Color(0xFF94A3B8)
                            )
                        }
                    }
                    if (resolutionText.isNotEmpty()) {
                        Text(
                            resolutionText,
                            fontSize = 11.sp,
                            color = Color(0xFF94A3B8),
                            modifier = Modifier.padding(top = 2.dp)
                        )
                    }

                    Spacer(modifier = Modifier.weight(1f))

                    // ── 底部信息 ──
                    HorizontalDivider(color = Color(0xFF1E293B), modifier = Modifier.padding(vertical = 8.dp))
                    Text(
                        "RK3588: 192.168.88.66",
                        fontSize = 10.sp,
                        color = Color(0xFF475569)
                    )
                    Text(
                        "TUN: 10.0.0.0/24 · USB 87Mbps",
                        fontSize = 10.sp,
                        color = Color(0xFF475569)
                    )
                    Text(
                        "VID 0x0BDA PID 0x8812",
                        fontSize = 10.sp,
                        color = Color(0xFF475569)
                    )
                }
            }

            // ═══ 右侧视频区域 ═══
            Surface(
                modifier = Modifier.weight(1f).fillMaxHeight().padding(4.dp),
                color = Color(0xFF020617),
                shape = androidx.compose.foundation.shape.RoundedCornerShape(8.dp)
            ) {
                Box(
                    modifier = Modifier.fillMaxSize(),
                    contentAlignment = Alignment.Center
                ) {
                    // 播放器画面
                    AndroidView(
                        factory = { context ->
                            SurfaceView(context).apply {
                                layoutParams = FrameLayout.LayoutParams(
                                    FrameLayout.LayoutParams.MATCH_PARENT,
                                    FrameLayout.LayoutParams.MATCH_PARENT
                                )
                                surfaceViewRef = this
                            }
                        },
                        modifier = Modifier.fillMaxSize()
                    )

                    // 未连接时提示
                    if (!isPlaying) {
                        Column(horizontalAlignment = Alignment.CenterHorizontally) {
                            Text(
                                if (!usbFound) "等待 USB 连接..."
                                else if (!vpnRunning) "启动 VPN 隧道"
                                else "输入 RTSP 地址并点击播放",
                                fontSize = 14.sp,
                                color = Color(0xFF475569)
                            )
                        }
                    }
                }
            }
        }
    }
}
