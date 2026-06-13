/**
 * MainActivity.kt — VPN 控制 + RTSP 播放器（同一界面）
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
import android.util.Log
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.tunnathub.app.service.TunNatVpnService
import com.tunnathub.app.usb.UsbBridge

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
            MainScreen(
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

@Composable
fun MainScreen(usbFound: Boolean, vpnRunning: Boolean, onVpnTap: () -> Unit) {
    MaterialTheme {
        Scaffold(
            topBar = {
                @OptIn(ExperimentalMaterial3Api::class)
                TopAppBar(title = { Text("TUN NAT Hub") })
            }
        ) { padding ->
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding)
                    .verticalScroll(rememberScrollState())
                    .padding(horizontal = 16.dp, vertical = 8.dp)
            ) {
                // ── VPN 状态卡 ──────────────────────────
                VpnCard(usbFound, vpnRunning, onVpnTap)

                Spacer(Modifier.height(12.dp))

                // ── RTSP 播放器 ─────────────────────────
                PlayerScreen()
            }
        }
    }
}

@Composable
fun VpnCard(usbFound: Boolean, vpnRunning: Boolean, onTap: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        colors = CardDefaults.cardColors(
            containerColor = if (vpnRunning)
                MaterialTheme.colorScheme.primaryContainer
            else
                MaterialTheme.colorScheme.surfaceVariant
        )
    ) {
        Row(
            modifier = Modifier.padding(12.dp),
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = if (vpnRunning) "● VPN 已连接" else "○ VPN 未连接",
                    style = MaterialTheme.typography.titleSmall
                )
                Text(
                    text = if (usbFound) "USB 已检测" else "USB 未连接",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )
            }
            Button(onClick = onTap, enabled = usbFound) {
                Text(if (vpnRunning) "断开" else "连接")
            }
        }
    }
}
