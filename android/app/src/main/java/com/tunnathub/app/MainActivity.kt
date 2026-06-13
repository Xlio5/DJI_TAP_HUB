/**
 * MainActivity.kt — 打开自动启动 VPN（串行授权: USB→VPN→Service）
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
    private var pendingVpnStart = false  // USB 授权后启动 VPN

    private val usbReceiver = object : BroadcastReceiver() {
        override fun onReceive(ctx: Context, intent: Intent) {
            if (USB_PERM_ACTION != intent.action) return
            if (intent.getBooleanExtra(UsbManager.EXTRA_PERMISSION_GRANTED, false)) {
                Log.i(TAG, "USB 权限已授予 → 请求 VPN 授权")
                requestVpn()
            } else {
                Log.w(TAG, "USB 权限被拒绝")
                pendingVpnStart = false
            }
        }
    }

    private val vpnLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == RESULT_OK) {
            Log.i(TAG, "VPN 授权通过 → 启动 Service")
            startTunService()
        } else {
            pendingVpnStart = false
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        registerReceiver(usbReceiver, IntentFilter(USB_PERM_ACTION),
            Context.RECEIVER_NOT_EXPORTED)

        usbDevice = findUsbDevice()

        setContent {
            TunNatScreen(
                usbFound = usbDevice != null,
                vpnRunning = isVpnRunning.value,
                onTap = {
                    if (isVpnRunning.value) {
                        stopTunService()
                    } else {
                        startAuthFlow()
                    }
                }
            )
        }

        // 自动启动（仅首次）
        if (usbDevice != null) {
            startAuthFlow()
        }
    }

    override fun onResume() {
        super.onResume()
        isVpnRunning.value = TunNatVpnService.isRunning
    }

    override fun onDestroy() {
        super.onDestroy()
        try { unregisterReceiver(usbReceiver) } catch (_: Exception) {}
    }

    // ── 授权流程：USB → VPN → Service ──────────
    private fun startAuthFlow() {
        if (pendingVpnStart) return
        pendingVpnStart = true

        val dev = usbDevice
        if (dev == null) {
            pendingVpnStart = false
            return
        }

        val um = getSystemService(USB_SERVICE) as UsbManager
        if (um.hasPermission(dev)) {
            // USB 已有权限，直接请求 VPN
            requestVpn()
        } else {
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
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
            startForegroundService(i) else startService(i)
        isVpnRunning.value = true
        pendingVpnStart = false
    }

    private fun stopTunService() {
        stopService(Intent(this, TunNatVpnService::class.java))
        isVpnRunning.value = false
        pendingVpnStart = false
    }

    private fun findUsbDevice(): UsbDevice? {
        val um = getSystemService(USB_SERVICE) as UsbManager
        for ((_, d) in um.deviceList)
            if (d.vendorId == UsbBridge.USB_VID && d.productId == UsbBridge.USB_PID) return d
        return null
    }
}

@Composable
fun TunNatScreen(usbFound: Boolean, vpnRunning: Boolean, onTap: () -> Unit) {
    MaterialTheme {
        Scaffold(
            topBar = { @OptIn(ExperimentalMaterial3Api::class)
                TopAppBar(title = { Text("TUN NAT Hub") }) }
        ) { padding ->
            Column(
                Modifier.fillMaxSize().padding(padding).padding(24.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Center
            ) {
                Text(if (usbFound) "USB 设备已检测到" else "未检测到 USB 设备",
                    color = if (usbFound) MaterialTheme.colorScheme.primary
                            else MaterialTheme.colorScheme.error)
                Spacer(Modifier.height(12.dp))
                Text(if (vpnRunning) "● VPN 已连接" else "○ VPN 未连接",
                    color = if (vpnRunning) MaterialTheme.colorScheme.primary
                            else MaterialTheme.colorScheme.onSurfaceVariant)
                Spacer(Modifier.height(20.dp))
                Button(onClick = onTap, enabled = usbFound) {
                    Text(if (vpnRunning) "停止 VPN" else "启动 VPN")
                }
            }
        }
    }
}
