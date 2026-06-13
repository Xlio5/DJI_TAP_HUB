/**
 * MainActivity.kt — TUN_NAT_HUB 主界面
 *
 * 功能:
 *   1. 请求 USB 设备权限
 *   2. 启动/停止 VPN Service
 *   3. 显示连接状态和统计信息
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
        private const val VPN_REQUEST_CODE = 100
    }

    private var usbDevice: UsbDevice? = null

    private val usbPermissionReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            if (USB_PERMISSION_ACTION == intent.action) {
                synchronized(this) {
                    val device = intent.getParcelableExtra<UsbDevice>(UsbManager.EXTRA_DEVICE)
                    if (intent.getBooleanExtra(UsbManager.EXTRA_PERMISSION_GRANTED, false)) {
                        Log.i(TAG, "USB 权限已授予: ${device?.deviceName}")
                        startVpnService()
                    } else {
                        Log.w(TAG, "USB 权限被拒绝: ${device?.deviceName}")
                        Toast.makeText(this@MainActivity, "USB 权限被拒绝，无法启动", Toast.LENGTH_LONG).show()
                    }
                }
            }
        }
    }

    // VPN 启动请求
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

        // 注册 USB 权限广播接收器
        registerReceiver(usbPermissionReceiver,
            IntentFilter(USB_PERMISSION_ACTION),
            Context.RECEIVER_NOT_EXPORTED
        )

        // 查找 USB 设备
        usbDevice = findUsbDevice()

        setContent {
            TunNatHubScreen(
                usbFound = usbDevice != null,
                onStart = ::requestUsbPermissionAndStart
            )
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        try {
            unregisterReceiver(usbPermissionReceiver)
        } catch (_: Exception) {}
    }

    /**
     * 请求 USB 权限，然后启动 VPN
     */
    private fun requestUsbPermissionAndStart() {
        val device = usbDevice
        if (device == null) {
            Toast.makeText(this, "未检测到 TUN_NAT_HUB USB 设备", Toast.LENGTH_LONG).show()
            return
        }

        val usbManager = getSystemService(USB_SERVICE) as UsbManager

        if (usbManager.hasPermission(device)) {
            // 已有权限，先请求 VPN 授权
            requestVpnPermission()
        } else {
            // 请求 USB 权限
            val permissionIntent = PendingIntent.getBroadcast(
                this, 0,
                Intent(USB_PERMISSION_ACTION).apply {
                    setPackage(packageName)
                },
                PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
            )
            usbManager.requestPermission(device, permissionIntent)
            Toast.makeText(this, "请授权 USB 设备访问", Toast.LENGTH_SHORT).show()
        }
    }

    /**
     * 请求 VPN 权限（系统弹窗）
     */
    private fun requestVpnPermission() {
        val intent = VpnService.prepare(this)
        if (intent != null) {
            vpnLauncher.launch(intent)
        } else {
            // 已有 VPN 权限
            startVpnService()
        }
    }

    /**
     * 启动 VpnService
     */
    private fun startVpnService() {
        val intent = Intent(this, TunNatVpnService::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            startForegroundService(intent)
        } else {
            startService(intent)
        }
        Toast.makeText(this, "TUN NAT Hub 已启动", Toast.LENGTH_SHORT).show()
    }

    /**
     * 查找匹配的 USB 设备
     */
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

// ── Compose UI ──────────────────────────────────────────────────

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun TunNatHubScreen(usbFound: Boolean, onStart: () -> Unit) {
    MaterialTheme {
        Scaffold(
            topBar = {
                TopAppBar(
                    title = { Text("TUN NAT Hub") }
                )
            }
        ) { padding ->
            Column(
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding)
                    .padding(24.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
                verticalArrangement = Arrangement.Center
            ) {
                // 状态指示
                Text(
                    text = if (usbFound) "USB 设备已检测到" else "未检测到 USB 设备",
                    style = MaterialTheme.typography.bodyLarge,
                    color = if (usbFound) MaterialTheme.colorScheme.primary
                            else MaterialTheme.colorScheme.error
                )

                Spacer(modifier = Modifier.height(8.dp))

                Text(
                    text = "VID: 0x${UsbBridge.USB_VID.toString(16).uppercase()}" +
                           "  PID: 0x${UsbBridge.USB_PID.toString(16).uppercase()}",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant
                )

                Spacer(modifier = Modifier.height(32.dp))

                // 启动按钮
                Button(
                    onClick = onStart,
                    enabled = usbFound
                ) {
                    Text("启动 VPN 隧道")
                }
            }
        }
    }
}
