/**
 * PlayerScreen.kt — 嵌入式 RTSP 播放器（EasyPlayer native SDK）
 */

package com.tunnathub.app

import android.content.Context
import android.os.Bundle
import android.os.Handler
import android.os.ResultReceiver
import android.util.Log
import android.view.SurfaceHolder
import android.view.SurfaceView
import android.widget.FrameLayout
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import org.easydarwin.video.EasyPlayerClient

@Composable
fun PlayerScreen(modifier: Modifier = Modifier) {
    val ctx = LocalContext.current

    var rtspUrl by remember { mutableStateOf("rtsp://192.168.88.100:554/stream1") }
    var isPlaying by remember { mutableStateOf(false) }
    var statusText by remember { mutableStateOf("") }
    var surfaceViewRef by remember { mutableStateOf<SurfaceView?>(null) }
    var playerRef by remember { mutableStateOf<EasyPlayerClient?>(null) }

    // 状态回调
    val receiver = remember {
        object : ResultReceiver(Handler(ctx.mainLooper)) {
            override fun onReceiveResult(code: Int, data: Bundle?) {
                when (code) {
                    EasyPlayerClient.RESULT_VIDEO_DISPLAYED -> {
                        statusText = "● 视频播放中"
                        isPlaying = true
                    }
                    EasyPlayerClient.RESULT_VIDEO_SIZE -> {
                        val w = data?.getInt(EasyPlayerClient.EXTRA_VIDEO_WIDTH, 0) ?: 0
                        val h = data?.getInt(EasyPlayerClient.EXTRA_VIDEO_HEIGHT, 0) ?: 0
                        statusText = "分辨率: ${w}x${h}"
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
                        statusText = "视频编码不支持"
                        isPlaying = false
                    }
                }
            }
        }
    }

    // 清理
    DisposableEffect(Unit) {
        onDispose {
            playerRef?.stop()
        }
    }

    Column(modifier = modifier.fillMaxWidth()) {
        Text(
            text = "RTSP 摄像头",
            style = MaterialTheme.typography.titleMedium,
            modifier = Modifier.padding(bottom = 4.dp)
        )

        // URL 输入
        Row(modifier = Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            OutlinedTextField(
                value = rtspUrl,
                onValueChange = { rtspUrl = it },
                modifier = Modifier.weight(1f),
                label = { Text("RTSP URL") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(
                    keyboardType = KeyboardType.Uri,
                    imeAction = ImeAction.Done
                )
            )

            Spacer(Modifier.width(8.dp))

            FilledIconButton(onClick = {
                if (isPlaying) {
                    playerRef?.stop()
                    playerRef = null
                    isPlaying = false
                    statusText = "已停止"
                } else {
                    val sv = surfaceViewRef ?: return@FilledIconButton
                    playUrl(ctx, rtspUrl, sv.holder, receiver) { client ->
                        playerRef = client
                        isPlaying = true
                        statusText = "连接中..."
                    }
                }
            }) {
                Icon(
                    if (isPlaying) Icons.Default.Stop else Icons.Default.PlayArrow,
                    contentDescription = if (isPlaying) "停止" else "播放"
                )
            }
        }

        // 状态
        if (statusText.isNotEmpty()) {
            Text(
                statusText,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.primary,
                modifier = Modifier.padding(vertical = 2.dp)
            )
        }

        Spacer(Modifier.height(8.dp))

        // SurfaceView
        Card(
            modifier = Modifier.fillMaxWidth().aspectRatio(16f / 9f),
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.surfaceContainerLow
            )
        ) {
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
        }
    }
}

private fun playUrl(
    ctx: Context,
    url: String,
    holder: SurfaceHolder,
    receiver: ResultReceiver,
    onReady: (EasyPlayerClient) -> Unit
) {
    try {
        val client = EasyPlayerClient(ctx, holder.surface, receiver)
        client.start(
            url,
            org.easydarwin.video.Client.TRANSTYPE_TCP,
            0,
            org.easydarwin.video.Client.EASY_SDK_VIDEO_FRAME_FLAG or
            org.easydarwin.video.Client.EASY_SDK_AUDIO_FRAME_FLAG,
            "", "", null
        )
        onReady(client)
    } catch (e: Exception) {
        Log.e("PlayerScreen", "播放失败", e)
    }
}
