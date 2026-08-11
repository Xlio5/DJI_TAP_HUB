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
        renderThreadStarted = false;
        frameNotified = false;
        nativeHandle = nativeCreate(this, rtspUrl, surface, sDecoderPreference);
        if (nativeHandle == 0) {
            running = false;
            callback.onError("gstreamer native create failed", null);
            return -1;
        }
        // 启动单一渲染线程 (长期存活, stop 时退出), 避免动态创建导致多线程并发
        renderThreadStarted = true;
        renderThread = new Thread(this::renderLoop, "GST_RENDER");
        renderThread.setDaemon(true);
        renderThread.start();
        return 0;
    }

    @Override
    public synchronized void stop() {
        running = false;
        // 唤醒渲染线程让它退出 (wait 超时兜底)
        synchronized (renderLock) {
            renderLock.notifyAll();
        }
        // 等渲染线程退出 (防 stop 后线程还访问 surface)
        Thread rt = renderThread;
        renderThread = null;
        if (rt != null) {
            try {
                rt.join(500);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }
        renderThreadStarted = false;
        frameNotified = false;
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

    // ── 渲染: 独立线程 + Bitmap 池, 不阻塞 GStreamer 流线程 ──
    private android.graphics.Bitmap renderBmp;    // 复用的 Bitmap
    private final Object renderLock = new Object();
    private byte[] pendingRgba;                    // 最新待渲染帧 (丢旧保新)
    private int pendingW, pendingH;
    private volatile boolean renderThreadStarted;
    private Thread renderThread;                   // 渲染线程 (start 时创建, stop 时停)

    // native 回调 Java: 收到解码帧 (RGBA), 只缓存最新帧, 渲染线程消费
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
        // 只保留最新帧 (丢旧保新), 渲染线程立即消费, 不阻塞流线程
        synchronized (renderLock) {
            pendingRgba = rgba;
            pendingW = width;
            pendingH = height;
            renderLock.notifyAll();   // 唤醒渲染线程
        }
        // start() 已创建渲染线程, 这里不再动态创建 (避免多线程并发 lockCanvas)
    }

    private int renderCount;   // 诊断: 渲染帧数

    private void renderLoop() {
        while (running) {
            // 阻塞等待新帧 (nativeOnFrame notify), 避免忙轮询空转 CPU
            byte[] rgba;
            int w, h;
            synchronized (renderLock) {
                while (running && pendingRgba == null) {
                    try {
                        renderLock.wait(100);   // 100ms 超时兜底, 防止漏 notify
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        return;
                    }
                }
                if (!running || pendingRgba == null) continue;
                rgba = pendingRgba;
                w = pendingW;
                h = pendingH;
                pendingRgba = null;
            }
            try {
                if (renderBmp == null || renderBmp.getWidth() != w || renderBmp.getHeight() != h) {
                    if (renderBmp != null) renderBmp.recycle();
                    renderBmp = android.graphics.Bitmap.createBitmap(w, h, android.graphics.Bitmap.Config.ARGB_8888);
                }
                renderBmp.copyPixelsFromBuffer(java.nio.ByteBuffer.wrap(rgba));
                android.graphics.Canvas canvas = surface.lockCanvas(null);
                if (canvas != null) {
                    canvas.drawBitmap(renderBmp, 0, 0, null);
                    surface.unlockCanvasAndPost(canvas);
                    renderCount++;
                    if (renderCount <= 3 || renderCount % 300 == 0) {
                        Log.i(TAG, "render #" + renderCount + " " + w + "x" + h);
                    }
                } else {
                    Log.w(TAG, "lockCanvas null");
                }
            } catch (Exception e) {
                Log.e(TAG, "render fail: " + e.getMessage());
            }
        }
    }
    private volatile boolean frameNotified;
}
