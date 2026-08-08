/**
 * RtspPlayer.kt — 调用外部 RTSP 播放器播放摄像头流
 *
 * Android 12+ 阻止 VPN 应用的 socket 匹配自身路由 (EPERM)，
 * 因此使用外部播放器 (EasyPlayer/VLC) 来播放 RTSP 流。
 * 外部 App 的 socket 不受 VPN EPERM 限制，可正常通过 TUN 隧道访问摄像头。
 */

package com.tunnathub.app

import android.content.Intent
import android.net.Uri
import android.widget.Toast
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp

@Composable
fun RtspPlayerPanel(modifier: Modifier = Modifier) {
    val context = LocalContext.current

    var rtspUrl by remember { mutableStateOf("rtsp://192.168.144.31:554/stream1") }

    Column(modifier = modifier.fillMaxWidth()) {
        Text(
            text = "RTSP 摄像头",
            style = MaterialTheme.typography.titleMedium,
            modifier = Modifier.padding(bottom = 4.dp)
        )

        OutlinedTextField(
            value = rtspUrl,
            onValueChange = { rtspUrl = it },
            modifier = Modifier.fillMaxWidth(),
            label = { Text("RTSP URL") },
            singleLine = true,
            keyboardOptions = KeyboardOptions(
                keyboardType = KeyboardType.Uri,
                imeAction = ImeAction.Done
            )
        )

        Spacer(Modifier.height(8.dp))

        // ── 播放按钮 ────────────────────────────────
        Button(
            onClick = {
                if (rtspUrl.isBlank()) {
                    Toast.makeText(context, "请输入 RTSP 地址", Toast.LENGTH_SHORT).show()
                    return@Button
                }
                try {
                    // 优先尝试 EasyPlayer 专用 Intent
                    val easyIntent = Intent(Intent.ACTION_VIEW).apply {
                        setDataAndType(Uri.parse(rtspUrl), "video/*")
                        setPackage("org.easydarwin.easyplayer")
                        addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    }
                    // 检查 EasyPlayer 是否可用
                    if (context.packageManager.resolveActivity(easyIntent, 0) != null) {
                        context.startActivity(easyIntent)
                    } else {
                        // 回退到系统通用 RTSP 播放器选择器
                        val genericIntent = Intent(Intent.ACTION_VIEW).apply {
                            setDataAndType(Uri.parse(rtspUrl), "video/*")
                            addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                        }
                        context.startActivity(genericIntent)
                    }
                } catch (e: Exception) {
                    Toast.makeText(context, "无法启动播放器: ${e.message}", Toast.LENGTH_LONG).show()
                }
            },
            modifier = Modifier.fillMaxWidth(),
            enabled = rtspUrl.isNotBlank()
        ) {
            Icon(Icons.Default.PlayArrow, contentDescription = null)
            Spacer(Modifier.width(8.dp))
            Text("打开 EasyPlayer 播放")
        }

        // ── 提示 ────────────────────────────────────
        Text(
            text = "点击按钮将调起 EasyPlayer 播放 RTSP 流。\n" +
                   "EasyPlayer 通过 VPN TUN 隧道访问摄像头。",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.padding(top = 4.dp)
        )
    }
}
