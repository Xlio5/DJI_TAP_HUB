package com.tunnathub.app.video

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.view.Surface
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.rtsp.RtspMediaSource
import com.tunnathub.app.util.AppLog
import org.easydarwin.video.RtspPlayerSession

class Media3RtspProbePlayer(
    context: Context,
    private val surface: Surface,
    private val callback: Callback
) : RtspPlayerSession {
    interface Callback {
        fun onVideoDisplayed()
        fun onError(message: String?)
    }

    private val appContext = context.applicationContext
    private val mainHandler = Handler(Looper.getMainLooper())
    private var player: ExoPlayer? = null
    private var firstFrame = false
    private var startMs = 0L

    fun start(url: String) {
        mainHandler.post {
            stopOnMain()
            firstFrame = false
            startMs = System.currentTimeMillis()
            val rtspSource = RtspMediaSource.Factory()
                .setTimeoutMs(4_000)
                .createMediaSource(MediaItem.fromUri(url))
            val exo = ExoPlayer.Builder(appContext).build()
            player = exo
            exo.addListener(object : Player.Listener {
                override fun onRenderedFirstFrame() {
                    if (firstFrame) return
                    firstFrame = true
                    val firstMs = System.currentTimeMillis() - startMs
                    val transportHint = if (firstMs >= 4_000) "疑似已回退TCP" else "疑似UDP直通"
                    AppLog.i("Media3Rtsp", "首帧已显示: ${firstMs}ms, $transportHint")
                    callback.onVideoDisplayed()
                }

                override fun onPlayerError(error: PlaybackException) {
                    AppLog.e("Media3Rtsp", "播放错误: ${error.errorCodeName} ${error.message}")
                    callback.onError("${error.errorCodeName}: ${error.message}")
                }
            })
            exo.setVideoSurface(surface)
            exo.setMediaSource(rtspSource)
            exo.prepare()
            exo.playWhenReady = true
            AppLog.i("Media3Rtsp", "open rtsp: $url (UDP优先, 4s无RTP则Media3回退TCP)")
        }
    }

    override fun stop() {
        mainHandler.post { stopOnMain() }
    }

    private fun stopOnMain() {
        val old = player ?: return
        player = null
        try {
            old.stop()
        } finally {
            old.release()
        }
    }
}
