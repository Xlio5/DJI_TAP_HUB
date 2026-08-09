/*
 * gstqgc_player.c — GStreamer 播放引擎 native 层
 *
 * 参考 QGC GstVideoReceiver 的 pipeline 逻辑:
 *   rtspsrc(latency=低, drop-on-latency=TRUE, protocols=UDP|TCP)
 *     → decodebin3 (自动选解码器)
 *     → GL sink (sync=false)
 *
 * JNI 导出:
 *   Java_com_tunnathub_app_video_GstQgcPlayer_nativeCreate
 *   Java_com_tunnathub_app_video_GstQgcPlayer_nativeDestroy
 *   Java_com_tunnathub_app_video_GstQgcPlayer_nativeSetLatency
 *   Java_com_tunnathub_app_video_GstQgcPlayer_nativeSetDropOnLatency
 */
#include <jni.h>
#include <android/log.h>
#include <android/native_window.h>
#include <gst/gst.h>
#include <gst/video/video.h>
#include <gst/rtsp/gstrtsptransport.h>
#include <gst/app/gstappsink.h>
#include <glib.h>
#include <string.h>

#define LOG_TAG "GstQgcPlayer"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO, LOG_TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, LOG_TAG, __VA_ARGS__)

static gint g_frame_count = 0;
static GstClockTime g_last_frame_pts = GST_CLOCK_TIME_NONE;
static JavaVM *g_java_vm = NULL;
static jobject g_java_instance = NULL;   // Java GstQgcPlayer 实例 (nativeOnFrame 回调用)

/* JNI_OnLoad: 保存 JavaVM 供 ANativeWindow_fromSurface 使用 */
JNIEXPORT jint JNICALL JNI_OnLoad(JavaVM *vm, void *reserved) {
    g_java_vm = vm;
    return JNI_VERSION_1_6;
}

static gboolean g_frame_notified = FALSE;

/* appsink new-sample: 收解码帧, 通过 JNI 通知 Java (首帧触发 onVideoDisplayed) */
static GstFlowReturn on_new_sample(GstAppSink *sink, gpointer user_data) {
    GstSample *sample = gst_app_sink_pull_sample(sink);
    if (sample) {
        GstBuffer *buf = gst_sample_get_buffer(sample);
        GstClockTime pts = GST_BUFFER_PTS(buf);
        g_frame_count++;
        if (g_frame_count <= 5 || g_frame_count % 100 == 0) {
            LOGI("appsink frame #%d pts=%" G_GUINT64_FORMAT " (interval=%dms)",
                 g_frame_count, pts,
                 g_last_frame_pts != GST_CLOCK_TIME_NONE
                     ? (int) GST_CLOCK_DIFF(g_last_frame_pts, pts) / GST_MSECOND : -1);
        }
        g_last_frame_pts = pts;

        // 通过 JNI 把帧传给 Java 渲染 (nativeOnFrame)
        if (g_java_instance && g_java_vm) {
            GstCaps *caps = gst_sample_get_caps(sample);
            int w = 0, h = 0;
            if (caps) {
                GstStructure *s = gst_caps_get_structure(caps, 0);
                gst_structure_get_int(s, "width", &w);
                gst_structure_get_int(s, "height", &h);
            }
            GstMapInfo map;
            if (w > 0 && h > 0 && gst_buffer_map(buf, &map, GST_MAP_READ)) {
                JNIEnv *env = NULL;
                if ((*g_java_vm)->AttachCurrentThread(g_java_vm, &env, NULL) == JNI_OK) {
                    jclass cls = (*env)->GetObjectClass(env, g_java_instance);
                    jmethodID mid = (*env)->GetMethodID(env, cls, "nativeOnFrame", "([BII)V");
                    if (mid) {
                        jbyteArray arr = (*env)->NewByteArray(env, map.size);
                        (*env)->SetByteArrayRegion(env, arr, 0, map.size, (const jbyte *) map.data);
                        (*env)->CallVoidMethod(env, g_java_instance, mid, arr, w, h);
                        (*env)->DeleteLocalRef(env, arr);
                        if (!g_frame_notified) {
                            g_frame_notified = TRUE;
                            LOGI("首帧帧数据已传 Java (%dx%d, %lu bytes)", w, h, (unsigned long) map.size);
                        }
                    }
                    (*env)->DeleteLocalRef(env, cls);
                    (*g_java_vm)->DetachCurrentThread(g_java_vm);
                }
                gst_buffer_unmap(buf, &map);
            }
        }
        gst_sample_unref(sample);
    }
    return GST_FLOW_OK;
}

// ── 静态插件注册 ──
// GStreamer Android SDK 静态库的插件需手动注册 (QGC 通过 gst_plugin_static_register 机制)
GST_PLUGIN_STATIC_DECLARE(rtsp);
GST_PLUGIN_STATIC_DECLARE(rtp);
GST_PLUGIN_STATIC_DECLARE(rtpmanager);
GST_PLUGIN_STATIC_DECLARE(playback);
GST_PLUGIN_STATIC_DECLARE(coreelements);
GST_PLUGIN_STATIC_DECLARE(app);
GST_PLUGIN_STATIC_DECLARE(videoconvertscale);
GST_PLUGIN_STATIC_DECLARE(videoparsersbad);
GST_PLUGIN_STATIC_DECLARE(androidmedia);
GST_PLUGIN_STATIC_DECLARE(typefindfunctions);
GST_PLUGIN_STATIC_DECLARE(tcp);
GST_PLUGIN_STATIC_DECLARE(udp);
GST_PLUGIN_STATIC_DECLARE(sdpelem);
GST_PLUGIN_STATIC_DECLARE(openh264);   // H264 软解 (QGC 用 openh264, 无需 JNI)
GST_PLUGIN_STATIC_DECLARE(opengl);     // glimagesink GL 渲染

/* GStreamer Android SDK 的 gst_init() 会自动调用本函数注册静态插件。
 * 这是 QGC/Android SDK 的标准做法，避免手动注册的重复/时序问题。 */
void gst_init_static_plugins(void) {
    GST_PLUGIN_STATIC_REGISTER(rtsp);
    GST_PLUGIN_STATIC_REGISTER(rtp);
    GST_PLUGIN_STATIC_REGISTER(rtpmanager);
    GST_PLUGIN_STATIC_REGISTER(playback);
    GST_PLUGIN_STATIC_REGISTER(coreelements);
    GST_PLUGIN_STATIC_REGISTER(app);
    GST_PLUGIN_STATIC_REGISTER(videoconvertscale);
    GST_PLUGIN_STATIC_REGISTER(videoparsersbad);
    GST_PLUGIN_STATIC_REGISTER(androidmedia);
    GST_PLUGIN_STATIC_REGISTER(typefindfunctions);
    GST_PLUGIN_STATIC_REGISTER(tcp);
    GST_PLUGIN_STATIC_REGISTER(udp);
    GST_PLUGIN_STATIC_REGISTER(sdpelem);
    GST_PLUGIN_STATIC_REGISTER(openh264);
    GST_PLUGIN_STATIC_REGISTER(opengl);
}

typedef struct _PlayerContext {
    GstElement *pipeline;
    GstElement *source;
    GstElement *sink;
    GMainLoop *loop;
    GThread *thread;
    gint width;
    gint height;
    gboolean running;
    JNIEnv *env;
    jobject javaCallback;
} PlayerContext;

static void on_pad_added(GstElement *element, GstPad *pad, gpointer user_data) {
    PlayerContext *ctx = (PlayerContext *) user_data;
    GstCaps *caps = gst_pad_get_current_caps(pad);
    if (!caps) {
        caps = gst_pad_query_caps(pad, NULL);
    }
    if (!caps) {
        return;
    }
    GstStructure *s = gst_caps_get_structure(caps, 0);
    const gchar *name = gst_structure_get_name(s);
    if (g_str_has_prefix(name, "video/")) {
        // decodebin3 已由 auto-plug 处理, 这里只记录分辨率
        int w = 0, h = 0;
        gst_structure_get_int(s, "width", &w);
        gst_structure_get_int(s, "height", &h);
        if (w > 0 && h > 0) {
            ctx->width = w;
            ctx->height = h;
            LOGI("video size %dx%d", w, h);
        }
    }
    gst_caps_unref(caps);
}

static gboolean on_bus_message(GstBus *bus, GstMessage *msg, gpointer user_data) {
    PlayerContext *ctx = (PlayerContext *) user_data;
    switch (GST_MESSAGE_TYPE(msg)) {
        case GST_MESSAGE_ERROR: {
            GError *err = NULL;
            gchar *debug = NULL;
            gst_message_parse_error(msg, &err, &debug);
            LOGE("GStreamer error: %s (%s)", err->message, debug ? debug : "");
            g_error_free(err);
            g_free(debug);
            break;
        }
        case GST_MESSAGE_EOS:
            LOGI("EOS");
            break;
        default:
            break;
    }
    return TRUE;
}

static gpointer player_thread(gpointer user_data) {
    PlayerContext *ctx = (PlayerContext *) user_data;
    gst_element_set_state(ctx->pipeline, GST_STATE_PLAYING);
    g_main_loop_run(ctx->loop);
    gst_element_set_state(ctx->pipeline, GST_STATE_NULL);
    return NULL;
}

/**
 * 构建 pipeline:
 *   rtspsrc(location=url, latency=latencyMs, drop-on-latency=TRUE,
 *           protocols=UDP|TCP, do-rtcp=TRUE, tcp-timeout, udp-reconnect=TRUE)
 *     → decodebin3 (自动选解码器)
 *     → appsink (同步 false, 丢旧保新)
 *
 * 解码器优先级通过 GST_PLUGIN_FEATURE_RANK 环境变量控制 (androidmedia 优先/avdec_h264 兜底)
 */
static PlayerContext *build_pipeline(const char *url, jobject surface,
                                     gint latency_ms, gboolean drop_on_latency) {
    PlayerContext *ctx = g_new0(PlayerContext, 1);
    ctx->running = TRUE;

    // 建 pipeline
    GError *error = NULL;
    // rtspsrc 动态 pad → 用 caps 限制只取 video/rtp, 避免 audio pad 协商失败拖累
    // port-range=10000-65534: 强制 RTP client_port >= 10000, V3s DNAT 只转发 10000+
    char *launch_str = g_strdup_printf(
        "rtspsrc location=%s latency=%d drop-on-latency=%s do-rtcp=TRUE "
        "udp-reconnect=TRUE tcp-timeout=20000000 port-range=10000-65534 name=source "
        "source. "
        "! application/x-rtp,media=video "
        "! rtph264depay "
        "! h264parse "
        "! openh264dec "
        "! videoconvert "
        "! video/x-raw,format=RGBA "
        "! appsink name=videoSink sync=false drop=true max-buffers=1",
        url, latency_ms, drop_on_latency ? "TRUE" : "FALSE");
    ctx->pipeline = gst_parse_launch(launch_str, &error);
    g_free(launch_str);
    if (error) {
        LOGE("pipeline parse failed: %s", error->message);
        g_error_free(error);
        g_free(ctx);
        return NULL;
    }

    // 强制 rtspsrc 用 UDP 传输 (GST_RTSP_LOWER_TRANS_UDP=1), 避免 TCP interleaved
    // 我们的 V3s DNAT 只转发 UDP 10000+, TCP interleaved 的 RTP 无法通过隧道
    GstElement *src = gst_bin_get_by_name(GST_BIN(ctx->pipeline), "source");
    if (src) {
        g_object_set(src, "protocols", (GstRTSPLowerTrans) (GST_RTSP_LOWER_TRANS_UDP), NULL);
        LOGI("rtspsrc protocols set to UDP only");
        gst_object_unref(src);
    }

    // 获取 rtspsrc 引用
    ctx->source = gst_bin_get_by_name(GST_BIN(ctx->pipeline), "source");
    if (!ctx->source) {
        LOGI("source name may differ, using first element");
    }

    // appsink 回调: 收解码帧, 通过 JNI 送到 Java GL 渲染
    GstElement *videoSink = gst_bin_get_by_name(GST_BIN(ctx->pipeline), "videoSink");
    if (videoSink) {
        g_object_set(videoSink, "emit-signals", TRUE, "sync", FALSE, NULL);
        GstAppSinkCallbacks callbacks = { NULL, NULL, on_new_sample };
        gst_app_sink_set_callbacks(GST_APP_SINK(videoSink), &callbacks, ctx, NULL);
        gst_object_unref(videoSink);
    }

    // bus 消息
    GstBus *bus = gst_element_get_bus(ctx->pipeline);
    gst_bus_add_watch(bus, on_bus_message, ctx);
    gst_object_unref(bus);

    ctx->loop = g_main_loop_new(NULL, FALSE);
    return ctx;
}

JNIEXPORT jlong JNICALL
Java_com_tunnathub_app_video_GstQgcPlayer_nativeCreate(JNIEnv *env, jclass clazz,
                                                        jobject jinstance, jstring jurl, jobject jsurface,
                                                        jint decoder_pref) {
    const char *url = (*env)->GetStringUTFChars(env, jurl, NULL);
    LOGI("nativeCreate url=%s pref=%d", url, decoder_pref);

    // 保存 Java 实例引用 (全局, 供 on_new_sample 回调 nativeOnFrame)
    if (g_java_instance) (*env)->DeleteGlobalRef(env, g_java_instance);
    g_java_instance = (*env)->NewGlobalRef(env, jinstance);

    // 初始化 GStreamer + 注册静态插件 (rtspsrc 等)
    static gboolean gst_inited = FALSE;
    if (!gst_inited) {
        // GST_DEBUG 必须在 gst_init 前设置才生效
        g_setenv("GST_DEBUG", "GST_CAPS:5,GST_PADS:5,rtspsrc:5,udpsrc:5,decodebin3:5,rtp*:5", FALSE);
        gst_init(NULL, NULL);   // gst_init 自动调用 gst_init_static_plugins() 注册静态插件
        gst_inited = TRUE;
        LOGI("GStreamer init (静态插件由 gst_init 自动注册)");
        // 打印已注册的 element 工厂，排查 rtspsrc/decodebin3 是否可用
        GstElementFactory *rtspsrc_f = gst_element_factory_find("rtspsrc");
        GstElementFactory *decodebin3_f = gst_element_factory_find("decodebin3");
        GstElementFactory *appsink_f = gst_element_factory_find("appsink");
        GstElementFactory *h264depay_f = gst_element_factory_find("rtph264depay");
        GstElementFactory *h264parse_f = gst_element_factory_find("h264parse");
        GstElementFactory *avdec_f = gst_element_factory_find("avdec_h264");
        GstElementFactory *android_dec_f = gst_element_factory_find("androidmedia");
        GstElementFactory *openh264dec_f = gst_element_factory_find("openh264dec");
        LOGI("factory check: rtspsrc=%s decodebin3=%s appsink=%s rtph264depay=%s h264parse=%s avdec_h264=%s androidmedia=%s openh264dec=%s",
             rtspsrc_f ? "OK" : "MISSING",
             decodebin3_f ? "OK" : "MISSING",
             appsink_f ? "OK" : "MISSING",
             h264depay_f ? "OK" : "MISSING",
             h264parse_f ? "OK" : "MISSING",
             avdec_f ? "OK" : "MISSING",
             android_dec_f ? "OK" : "MISSING",
             openh264dec_f ? "OK" : "MISSING");
        // 列出所有 video 解码器, 确认到底有没有 H264 解码可用
        if (!avdec_f && !android_dec_f && !openh264dec_f) {
            GList *features = gst_registry_get_feature_list_by_plugin(gst_registry_get(),
                    "androidmedia");
            if (features) {
                for (GList *l = features; l; l = l->next) {
                    GstPluginFeature *f = (GstPluginFeature *) l->data;
                    LOGI("androidmedia feature: %s", gst_plugin_feature_get_name(f));
                    gst_object_unref(f);
                }
                g_list_free(features);
            }
        }
        if (rtspsrc_f) gst_object_unref(rtspsrc_f);
        if (decodebin3_f) gst_object_unref(decodebin3_f);
        if (appsink_f) gst_object_unref(appsink_f);
        if (h264depay_f) gst_object_unref(h264depay_f);
        if (h264parse_f) gst_object_unref(h264parse_f);
        if (avdec_f) gst_object_unref(avdec_f);
        if (android_dec_f) gst_object_unref(android_dec_f);
        if (openh264dec_f) gst_object_unref(openh264dec_f);
    }

    // 解码器优先级: 1=androidmedia(硬解) 2=avdec_h264(软解) 0=auto
    // QGC 用 decodebin3 自动选, 这里先 auto, 解码器选项后续在 Java 层暴露
    gint latency_ms = 40;          // 低延迟: 40ms 接收缓冲预算
    gboolean drop = TRUE;          // drop-on-latency: 丢旧保新
    PlayerContext *ctx = build_pipeline(url, jsurface, latency_ms, drop);
    (*env)->ReleaseStringUTFChars(env, jurl, url);
    if (!ctx) {
        return 0;
    }
    // 启动 GL 主循环线程
    ctx->thread = g_thread_new("gst-player", player_thread, ctx);
    return (jlong) ctx;
}

JNIEXPORT void JNICALL
Java_com_tunnathub_app_video_GstQgcPlayer_nativeDestroy(JNIEnv *env, jclass clazz, jlong handle) {
    PlayerContext *ctx = (PlayerContext *) handle;
    if (!ctx) return;
    ctx->running = FALSE;
    if (ctx->loop) {
        g_main_loop_quit(ctx->loop);
    }
    if (ctx->thread) {
        g_thread_join(ctx->thread);
    }
    if (ctx->pipeline) {
        gst_element_set_state(ctx->pipeline, GST_STATE_NULL);
        gst_object_unref(ctx->pipeline);
    }
    g_free(ctx);
}

JNIEXPORT void JNICALL
Java_com_tunnathub_app_video_GstQgcPlayer_nativeSetLatency(JNIEnv *env, jclass clazz,
                                                            jlong handle, jint latency_ms) {
    PlayerContext *ctx = (PlayerContext *) handle;
    if (!ctx || !ctx->source) return;
    g_object_set(ctx->source, "latency", (guint) latency_ms, NULL);
}

JNIEXPORT void JNICALL
Java_com_tunnathub_app_video_GstQgcPlayer_nativeSetDropOnLatency(JNIEnv *env, jclass clazz,
                                                                 jlong handle, jboolean drop) {
    PlayerContext *ctx = (PlayerContext *) handle;
    if (!ctx || !ctx->source) return;
    g_object_set(ctx->source, "drop-on-latency", drop ? TRUE : FALSE, NULL);
}
