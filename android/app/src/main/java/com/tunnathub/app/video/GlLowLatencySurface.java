package com.tunnathub.app.video;

import android.content.Context;
import android.graphics.SurfaceTexture;
import android.opengl.GLES11Ext;
import android.opengl.GLES20;
import android.opengl.GLSurfaceView;
import android.opengl.Matrix;
import android.util.Log;
import android.view.Surface;

import javax.microedition.khronos.egl.EGLConfig;
import javax.microedition.khronos.opengles.GL10;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.FloatBuffer;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;

/**
 * 低延迟视频渲染：MediaCodec → SurfaceTexture → OpenGL 立即渲染最新帧。
 *
 * <p>绕开 SurfaceView 的 buffer 队列 + vsync 累积延迟：
 * <ul>
 *   <li>MediaCodec 输出到 {@link SurfaceTexture}（而非 SurfaceView 的 Surface）；</li>
 *   <li>收到 {@code onFrameAvailable} 后 GL 线程立即 updateTexImage + 渲染最新帧；</li>
 *   <li>不像 SurfaceView 那样攒 2-3 帧才合成上屏，延迟接近 1 帧 vsync。</li>
 * </ul>
 *
 * <p>参考 QGC 的 GL sink "丢旧保新"：只渲染最新纹理。
 * 纹理 id 在 GL 线程（onSurfaceCreated）生成，SurfaceTexture 关联该 id；
 * getSurface() 阻塞等待 GL 就绪后返回，避免时序竞态。
 */
public final class GlLowLatencySurface implements GLSurfaceView.Renderer, SurfaceTexture.OnFrameAvailableListener {
    private static final String TAG = "GlLowLatencySurface";

    private final GLSurfaceView glView;
    private final CountDownLatch glReady = new CountDownLatch(1);
    private final AtomicBoolean frameAvailable = new AtomicBoolean(false);

    private volatile SurfaceTexture surfaceTexture;
    private volatile Surface surface;
    private int texId;

    // GL 状态
    private int program;
    private FloatBuffer vertexBuf;
    private FloatBuffer texCoordBuf;

    public GlLowLatencySurface(Context context) {
        glView = new GLSurfaceView(context);
        glView.setEGLContextClientVersion(2);
        glView.setRenderer(this);
        // CONTINUOUSLY: 持续渲染, 保证 MediaCodec 输出 buffer 总是被及时 updateTexImage 释放,
        // 避免解码器输出积压(DecBuffFrms 缓存)导致延迟。
        glView.setRenderMode(GLSurfaceView.RENDERMODE_CONTINUOUSLY);
    }

    /** MediaCodec configure 用的 Surface（指向 SurfaceTexture）。阻塞等待 GL 就绪。 */
    public Surface getSurface() {
        try {
            if (!glReady.await(3, TimeUnit.SECONDS)) {
                Log.e(TAG, "GL 初始化超时");
            }
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
        return surface;
    }

    public GLSurfaceView getView() {
        return glView;
    }

    public void release() {
        frameAvailable.set(false);
        Surface s = surface;
        surface = null;
        if (s != null) {
            try {
                s.release();
            } catch (Exception ignored) {
            }
        }
        SurfaceTexture st = surfaceTexture;
        surfaceTexture = null;
        if (st != null) {
            st.release();
        }
    }

    @Override
    public void onFrameAvailable(SurfaceTexture st) {
        frameAvailable.set(true);
        glView.requestRender();
    }

    // ── GLSurfaceView.Renderer ──

    @Override
    public void onSurfaceCreated(GL10 gl, EGLConfig config) {
        initGl();
    }

    @Override
    public void onSurfaceChanged(GL10 gl, int width, int height) {
        GLES20.glViewport(0, 0, width, height);
    }

    @Override
    public void onDrawFrame(GL10 gl) {
        SurfaceTexture st = surfaceTexture;
        if (st == null) {
            return;
        }
        // 持续 updateTexImage: 及时释放 MediaCodec 输出 buffer, 避免解码器积压(DecBuffFrms)
        // 即使无新帧也调用(可能抛异常), 保证输出通道畅通
        boolean hasNew = false;
        try {
            hasNew = true;
            st.updateTexImage();   // 拿最新视频帧，并通知 MediaCodec 释放该 buffer
        } catch (Exception e) {
            hasNew = false;        // 无新帧(buffer 已被消费完), 保持通道畅通
        }
        if (!hasNew && !frameAvailable.getAndSet(false)) {
            return;
        }
        // 渲染最新纹理到屏幕（丢旧保新：只画最新帧）
        GLES20.glClearColor(0, 0, 0, 1);
        GLES20.glClear(GLES20.GL_COLOR_BUFFER_BIT);
        GLES20.glUseProgram(program);
        GLES20.glActiveTexture(GLES20.GL_TEXTURE0);
        GLES20.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, texId);
        GLES20.glEnableVertexAttribArray(0);
        GLES20.glVertexAttribPointer(0, 2, GLES20.GL_FLOAT, false, 0, vertexBuf);
        GLES20.glEnableVertexAttribArray(1);
        GLES20.glVertexAttribPointer(1, 2, GLES20.GL_FLOAT, false, 0, texCoordBuf);
        GLES20.glDrawArrays(GLES20.GL_TRIANGLE_STRIP, 0, 4);
        GLES20.glDisableVertexAttribArray(0);
        GLES20.glDisableVertexAttribArray(1);
    }

    private void initGl() {
        // 生成 OES 外部纹理，SurfaceTexture 关联该 id
        int[] tex = new int[1];
        GLES20.glGenTextures(1, tex, 0);
        texId = tex[0];
        GLES20.glBindTexture(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, texId);
        GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES20.GL_TEXTURE_MIN_FILTER, GLES20.GL_LINEAR);
        GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES20.GL_TEXTURE_MAG_FILTER, GLES20.GL_LINEAR);
        GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES20.GL_TEXTURE_WRAP_S, GLES20.GL_CLAMP_TO_EDGE);
        GLES20.glTexParameteri(GLES11Ext.GL_TEXTURE_EXTERNAL_OES, GLES20.GL_TEXTURE_WRAP_T, GLES20.GL_CLAMP_TO_EDGE);
        surfaceTexture = new SurfaceTexture(texId);
        surfaceTexture.setOnFrameAvailableListener(this);
        surface = new Surface(surfaceTexture);

        // 顶点 + 纹理坐标（全屏，Y 翻转适配视频方向）
        float[] vertices = {-1, -1, 1, -1, -1, 1, 1, 1};
        float[] texCoords = {0, 1, 1, 1, 0, 0, 1, 0};
        vertexBuf = toFloatBuffer(vertices);
        texCoordBuf = toFloatBuffer(texCoords);

        String vs = "attribute vec2 aPos; attribute vec2 aTex; varying vec2 vTex;"
                + "void main() { gl_Position = vec4(aPos, 0.0, 1.0); vTex = aTex; }";
        String fs = "#extension GL_OES_EGL_image_external : require\n"
                + "precision mediump float; varying vec2 vTex; uniform samplerExternalOES uTex;"
                + "void main() { gl_FragColor = texture2D(uTex, vTex); }";
        program = buildProgram(vs, fs);

        glReady.countDown();
        Log.i(TAG, "GL surface 就绪 texId=" + texId);
    }

    private static FloatBuffer toFloatBuffer(float[] data) {
        ByteBuffer bb = ByteBuffer.allocateDirect(data.length * 4);
        bb.order(ByteOrder.nativeOrder());
        FloatBuffer fb = bb.asFloatBuffer();
        fb.put(data);
        fb.position(0);
        return fb;
    }

    private static int buildProgram(String vsSrc, String fsSrc) {
        int vs = compileShader(GLES20.GL_VERTEX_SHADER, vsSrc);
        int fs = compileShader(GLES20.GL_FRAGMENT_SHADER, fsSrc);
        int prog = GLES20.glCreateProgram();
        GLES20.glAttachShader(prog, vs);
        GLES20.glAttachShader(prog, fs);
        GLES20.glLinkProgram(prog);
        int[] ok = new int[1];
        GLES20.glGetProgramiv(prog, GLES20.GL_LINK_STATUS, ok, 0);
        if (ok[0] == 0) {
            Log.e(TAG, "program link failed: " + GLES20.glGetProgramInfoLog(prog));
        }
        return prog;
    }

    private static int compileShader(int type, String src) {
        int sh = GLES20.glCreateShader(type);
        GLES20.glShaderSource(sh, src);
        GLES20.glCompileShader(sh);
        int[] ok = new int[1];
        GLES20.glGetShaderiv(sh, GLES20.GL_COMPILE_STATUS, ok, 0);
        if (ok[0] == 0) {
            Log.e(TAG, "shader compile failed: " + GLES20.glGetShaderInfoLog(sh));
        }
        return sh;
    }
}
