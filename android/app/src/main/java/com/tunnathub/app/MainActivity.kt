/**
 * MainActivity.kt — TUN_NAT_HUB 主界面
 *
 * 打开 App 自动启动 VPN。
 * 连接流程: USB 权限 → VPN 授权 → 启动 Service
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
        private const val USB_PERMISSION_ACTION = "com.tunnathub.app.USB_PERMISSION"
    }

    private var usbDevice: UsbDevice? = null
    private var autoStarted = false
    private var isVpnRunning = mutableStateOf(false)

    private val usbPermissionReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            if (USB_PERMISSION_ACTION == intent.action) {
                synchronized(this) {
                    val device = intent.getParcelableExtra<UsbDevice>(UsbManager.EXTRA_DEVICE)
                    if (intent.getBooleanExtra(UsbManager.EXTRA_PERMISSION_GRANTED, false)) {
                        Log.i(TAG, "USB 权限已授予")
                        requestVpnPermission()
                    } else {
                        Log.w(TAG, "USB 权限被拒绝")
                        Toast.makeText(this@MainActivity, "USB 权限被拒绝", Toast.LENGTH_LONG).show()
                    }
                }
            }
        }
    }

    private val vpnLauncher = registerForActivityResult(
        ActivityResultContracts.StartActivityForResult()
    ) { result ->
        if (result.resultCode == RESULT_OK) {
            Log.i(TAG, "VPN 授权通过")
            startVpnService()
        } else {
            Toast.makeText(this, "VPN 权限未授予", Toast.LENGTH_LONG).show()
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        registerReceiver(usbPermissionReceiver,
            IntentFilter(USB_PERMISSION_ACTION),
            Context.RECEIVER_NOT_EXPORTED)

        usbDevice = findUsbDevice()

        setContent {
            TunNatHubScreen(
                usbFound = usbDevice != null,
                vpnRunning = isVpnRunning.value,
                onStartStop = {
                    if (isVpnRunning.value) {
                        stopVpnService()
                    } else {
                        autoStartVpn()
                    }
                }
            )
        }

        // 自动启动 VPN
        if (!autoStarted && usbDevice != null) {
            autoStarted = true
            autoStartVpn()
        }
    }

    override fun onResume() {
        super.onResume()
        // 返回界面时刷新 VPN 状态
        checkVpnStatus()
    }

    override fun onDestroy() {
        super.onDestroy()
        try { unregisterReceiver(usbPermissionReceiver) } catch (_: Exception) {}
    }

    private fun autoStartVpn() {
        val device = usbDevice
        if (device == null) {
            Toast.makeText(this, "未检测到 USB 设备", Toast.LENGTH_LONG).show()
            return
        }

        val usbManager = getSystemService(USB_SERVICE) as UsbManager
        if (usbManager.hasPermission(device)) {
            requestVpnPermission()
        } else {
            val permissionIntent = PendingIntent.getBroadcast(
                this, 0,
                Intent(USB_PERMISSION_ACTION).apply { setPackage(packageName) },
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
            )
            usbManager.requestPermission(device, permissionIntent)
        }
    }

    private fun requestVpnPermission() {
        val intent = VpnService.prepare(this)
        if (intent != null) {
            vpnLauncher.launch(intent)
        } else {
            startVpnService()
        }
    }

    private fun startVpnService() {
        val intent = Intent(this, TunNatVpnService::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(intent)
        } else {
            startService(intent)
        }
        isVpnRunning.value = true
        Log.i(TAG, "VPN Service 已启动")
    }

    private fun stopVpnService() {
        stopService(Intent(this, TunNatVpnService::class.java))
        isVpnRunning.value = false
    }

    private fun checkVpnStatus() {
        isVpnRunning.value = TunNatVpnService.isRunning
    }

    private fun findUsbDevice(): UsbDevice? {
        val usbManager = getSystemService(USB_SERVICE) as UsbManager
        for ((_, device) in usbManager.deviceList) {
            if (device.vendorId == UsbBridge.USB_VID && device.productId == UsbBridge.USB_PID) {
                Log.i(TAG, "找到 USB 设备: ${device.deviceName}")
                return device
            }
        }
        Log.w(TAG, "未找到 TUN_NAT_HUB USB 设备")
        return null
    }
}

@Composable
fun TunNatHubScreen(usbFound: Boolean, vpnRunning: Boolean, onStartStop: () -> Unit) {
    MaterialTheme {
        Scaffold(
            topBar = {
                @OptIn(ExperimentalMaterial3Api::class)
                TopAppBar(title = { Text("TUN NAT Hub") })
            }
        ) { padding ->
            Column(
                modifier = Modifier.fillMaxSize().padding(padding).padding(24.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Center
            ) {
                Text(
                    text = if (usbFound) "USB 设备已检测到" else "未检测到 USB 设备",
                    style = MaterialTheme.typography.bodyLarge,
                    color = if (usbFound) MaterialTheme.colorScheme.primary
                            else MaterialTheme.colorScheme.error
                )

                Spacer(modifier = Modifier.height(16.dp))

                Text(
                    text = if (vpnRunning) "● VPN 隧道已连接" else "○ VPN 未连接",
                    style = MaterialTheme.typography.bodyLarge,
                    color = if (vpnRunning) MaterialTheme.colorScheme.primary
                            else MaterialTheme.colorScheme.onSurfaceVariant
                )

                Spacer(modifier = Modifier.height(24.dp))

                Button(onClick = onStartStop, enabled = usbFound) {
                    Text(if (vpnRunning) "停止 VPN" else "启动 VPN")
                }
            }
        }
    }
}
