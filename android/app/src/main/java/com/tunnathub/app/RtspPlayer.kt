/**
 * RtspPlayer.kt — 嵌入式 RTSP 播放器（基于 Media3 ExoPlayer）
 *
 * 参考 EasyPlayer 界面风格: URL 输入 + 播放/停止按钮 + 视频窗口
 * 通过 VPN 隧道访问局域网摄像头。
 */

package com.tunnathub.app

import android.annotation.SuppressLint
import android.view.SurfaceView
import android.widget.FrameLayout
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.KeyboardActions
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.input.ImeAction
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.rtsp.RtspMediaSource
import androidx.media3.exoplayer.source.MediaSource
import androidx.media3.ui.PlayerView

@SuppressLint("RememberReturnType")
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RtspPlayerPanel(modifier: Modifier = Modifier) {
    val context = LocalContext.current
    val focusManager = LocalFocusManager.current

    // 默认摄像头 URL
    var rtspUrl by remember { mutableStateOf("rtsp://172.24.91.28:554/stream1") }
    var isPlaying by remember { mutableStateOf(false) }
    var errorMsg by remember { mutableStateOf<String?>(null) }

    // ExoPlayer 实例
    val player = remember {
        ExoPlayer.Builder(context)
            .build()
            .apply {
                playWhenReady = true
                repeatMode = Player.REPEAT_MODE_OFF
                addListener(object : Player.Listener {
                    override fun onPlayerError(error: androidx.media3.common.PlaybackException) {
                        errorMsg = "播放错误: ${error.localizedMessage ?: "未知错误"}"
                        isPlaying = false
                    }
                    override fun onPlaybackStateChanged(state: Int) {
                        if (state == Player.STATE_READY) {
                            errorMsg = null
                        }
                    }
                })
            }
    }

    // 组件销毁时释放播放器
    DisposableEffect(Unit) {
        onDispose { player.release() }
    }

    Column(modifier = modifier.fillMaxWidth()) {
        // ── 标题 ──────────────────────────────────────
        Text(
            text = "RTSP 摄像头",
            style = MaterialTheme.typography.titleMedium,
            modifier = Modifier.padding(bottom = 4.dp)
        )

        // ── URL 输入 + 播放按钮 ──────────────────────
        Row(
            modifier = Modifier.fillMaxWidth(),
            verticalAlignment = Alignment.CenterVertically
        ) {
            OutlinedTextField(
                value = rtspUrl,
                onValueChange = { rtspUrl = it },
                modifier = Modifier.weight(1f),
                label = { Text("RTSP URL") },
                singleLine = true,
                keyboardOptions = KeyboardOptions(
                    keyboardType = KeyboardType.Uri,
                    imeAction = ImeAction.Go
                ),
                keyboardActions = KeyboardActions(
                    onGo = {
                        focusManager.clearFocus()
                        playRtsp(player, rtspUrl, isPlaying) { playing, err ->
                            isPlaying = playing; errorMsg = err
                        }
                    }
                ),
                isError = errorMsg != null
            )

            Spacer(Modifier.width(8.dp))

            // 播放/停止按钮
            FilledIconButton(
                onClick = {
                    focusManager.clearFocus()
                    if (isPlaying) {
                        player.stop()
                        isPlaying = false
                    } else {
                        playRtsp(player, rtspUrl, isPlaying) { playing, err ->
                            isPlaying = playing; errorMsg = err
                        }
                    }
                }
            ) {
                if (isPlaying) {
                    Icon(Icons.Default.Stop, contentDescription = "停止")
                } else {
                    Icon(Icons.Default.PlayArrow, contentDescription = "播放")
                }
            }
        }

        // ── 错误提示 ──────────────────────────────────
        if (errorMsg != null) {
            Text(
                text = errorMsg!!,
                color = MaterialTheme.colorScheme.error,
                style = MaterialTheme.typography.bodySmall,
                modifier = Modifier.padding(top = 2.dp)
            )
        }

        Spacer(Modifier.height(8.dp))

        // ── 播放器视图 ────────────────────────────────
        Card(
            modifier = Modifier
                .fillMaxWidth()
                .aspectRatio(16f / 9f),
            colors = CardDefaults.cardColors(
                containerColor = MaterialTheme.colorScheme.surfaceContainerLow
            )
        ) {
            if (isPlaying) {
                AndroidView(
                    factory = { ctx ->
                        PlayerView(ctx).apply {
                            this.player = player
                            useController = true  // 显示播放控制
                            resizeMode = androidx.media3.ui.AspectRatioFrameLayout.RESIZE_MODE_FIT
                            layoutParams = FrameLayout.LayoutParams(
                                FrameLayout.LayoutParams.MATCH_PARENT,
                                FrameLayout.LayoutParams.MATCH_PARENT
                            )
                        }
                    },
                    modifier = Modifier.fillMaxSize()
                )
            } else {
                // 播放前显示提示
                Box(
                    modifier = Modifier.fillMaxSize(),
                    contentAlignment = Alignment.Center
                ) {
                    Text(
                        text = if (errorMsg != null) "播放失败" else "输入 RTSP 地址并点击播放",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant
                    )
                }
            }
        }
    }
}

/**
 * 使用 RtspMediaSource.Factory 播放 RTSP 流
 */
private fun playRtsp(
    player: ExoPlayer,
    url: String,
    currentlyPlaying: Boolean,
    onResult: (Boolean, String?) -> Unit
) {
    if (url.isBlank()) {
        onResult(false, "请输入 RTSP 地址")
        return
    }

    try {
        player.stop()

        val factory = RtspMediaSource.Factory()
        val mediaSource: MediaSource = factory.createMediaSource(MediaItem.fromUri(url))
        player.setMediaSource(mediaSource)
        player.prepare()
        player.play()

        onResult(true, null)
    } catch (e: Exception) {
        onResult(false, "播放异常: ${e.localizedMessage ?: e.message}")
    }
}
