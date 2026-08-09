package com.tunnathub.app.video;

import android.content.Context;
import android.util.Log;
import android.view.Surface;

import org.easydarwin.video.BenchmarkStats;
import org.easydarwin.video.RtspPlayerSession;

/**
 * GStreamer 播放引擎（参考 QGC GstVideoReceiver 逻辑）。
 *
 * <p>pipeline 对齐 QGC 低延迟模式：
 * <pre>
 *   rtspsrc(latency=低, drop-on-latency=TRUE, protocols=UDP|TCP)
 *     → decodebin3 (自动选解码器: androidmedia 硬解优先, avdec_h264 软解兜底)
 *     → GL sink (sync=false, 帧到即显示)
 * </pre>
 *
 * <p>关键参数（对应 QGC VideoSettings）：
 * <ul>
 *   <li>latency: rtspsrc 接收缓冲预算（低延迟模式忽略，设为 0-40ms）</li>
 *   <li>drop-on-latency: TRUE（超时丢帧，丢旧保新）</li>
 *   <li>sink sync=false: 不等时钟，帧到即显示</li>
 * </ul>
 *
 * <p>native 层在 GStreamer SDK 集成后提供（libgstqgcplayer.so）。
 */
public final class GstQgcPlayer implements RtspPlayerSession {
    public interface Callback {
        void onVideoDisplayed(String decoderName);
        void onVideoSize(int width, int height);
        void onTimeout();
        void onError(String message, Throwable error);
        default void onStats(BenchmarkStats.Snapshot snapshot) {}
        default void onDecoderChanged(String decoderName) {}
    }

    private static final String TAG = "GstQgcPlayer";
    private static final String NATIVE_LIB = "gstqgcplayer";

    // 解码器优先级: 1=hardware(androidmedia) 2=software(avdec_h264) 0=auto
    private static volatile int sDecoderPreference = 0;

    private final Context context;
    private final Surface surface;
    private final Callback callback;
    private final String rtspUrl;

    private long nativeHandle;
    private volatile boolean running;

    static {
        try {
            System.loadLibrary(NATIVE_LIB);
        } catch (UnsatisfiedLinkError e) {
            Log.e(TAG, "GStreamer native 库加载失败: " + e.getMessage());
        }
    }

    public GstQgcPlayer(Context context, Surface surface, Callback callback, String rtspUrl) {
        this.context = context.getApplicationContext();
        this.surface = surface;
        this.callback = callback;
        this.rtspUrl = rtspUrl;
    }

    public static void setDecoderPreference(int pref) {
        sDecoderPreference = pref;
        Log.i(TAG, "decoder preference: " + pref + " (1=hardware 2=software 0=auto)");
    }

    public static int getDecoderPreference() {
        return sDecoderPreference;
    }

    public synchronized int start() {
        if (running) stop();
        running = true;
        nativeHandle = nativeCreate(this, rtspUrl, surface, sDecoderPreference);
        if (nativeHandle == 0) {
            running = false;
            callback.onError("gstreamer native create failed", null);
            return -1;
        }
        return 0;
    }

    @Override
    public synchronized void stop() {
        running = false;
        if (nativeHandle != 0) {
            nativeDestroy(nativeHandle);
            nativeHandle = 0;
        }
    }

    // ── JNI ──
    private static native long nativeCreate(Object instance, String url, Surface surface, int decoderPref);
    private static native void nativeDestroy(long handle);
    private static native void nativeSetLatency(long handle, int latencyMs);
    private static native void nativeSetDropOnLatency(long handle, boolean drop);

    // native 回调 Java: 收到解码帧 (RGBA), 用 Canvas 画到 SurfaceView
    @SuppressWarnings("unused")
    private void nativeOnFrame(byte[] rgba, int width, int height) {
        if (!running) return;
        if (width <= 0 || height <= 0) return;
        if (rgba == null || rgba.length < width * height * 4) return;
        // 首次帧: 通知 UI
        if (!frameNotified) {
            frameNotified = true;
            if (callback != null) {
                callback.onVideoDisplayed("openh264dec");
                callback.onVideoSize(width, height);
            }
        }
        // 用 Bitmap + Canvas 画到 Surface（低延迟：不经过 Bitmap 复用队列，直接画）
        android.graphics.Bitmap bmp = null;
        android.graphics.Canvas canvas = null;
        try {
            bmp = android.graphics.Bitmap.createBitmap(width, height, android.graphics.Bitmap.Config.ARGB_8888);
            bmp.copyPixelsFromBuffer(java.nio.ByteBuffer.wrap(rgba));
            canvas = surface.lockCanvas(null);
            if (canvas != null) {
                canvas.drawBitmap(bmp, null,
                        new android.graphics.Rect(0, 0, surfaceWidth(), surfaceHeight()), null);
                surface.unlockCanvasAndPost(canvas);
            }
        } catch (Exception e) {
            // 渲染失败忽略（下一帧重试）
        } finally {
            if (bmp != null) bmp.recycle();
        }
    }
    private volatile boolean frameNotified;

    // Surface 无宽高 API, 用视频帧原始尺寸绘制 (Canvas 会缩放到 Surface)
    private int surfaceWidth() {
        return 1280;
    }

    private int surfaceHeight() {
        return 720;
    }
}
