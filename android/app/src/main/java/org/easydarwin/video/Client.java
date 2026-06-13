package org.easydarwin.video;

import android.Manifest;
import android.content.Context;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import androidx.core.content.ContextCompat;
import android.util.Log;
import android.util.SparseArray;

import java.io.Closeable;
import java.io.FileNotFoundException;
import java.io.FileOutputStream;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.charset.StandardCharsets;
import java.util.HashSet;
import java.util.Set;

/**
 * Created by John on 2016/3/12.
 */
public class Client implements Closeable {

    private static int sKey;
    private static Context mContext;
    private volatile int paused = 0;
    private static final Handler h = new Handler(Looper.getMainLooper());
    private static Set<Integer> _channelPause = new HashSet<>();
    private final Runnable closeTask = new Runnable() {
        @Override
        public void run() {
            if (paused > 0) {
                Log.i(TAG, "realPause! close stream");
                closeStream();
                paused = 2;
            }
        }
    };

    private int _channel;
    private String _url;
    private int _type;
    private int _mediaType;
    private String _user;
    private String _pwd;
    private int _sendOption;

    public static final class FrameInfo {
        public int codec;           /* 闊宠棰戞牸寮?*/

        public int type;            /* 瑙嗛甯х被鍨?*/
        public byte fps;            /* 瑙嗛甯х巼 */
        public short width;         /* 瑙嗛瀹?*/
        public short height;        /* 瑙嗛楂?*/

        public int reserved1;       /* 淇濈暀鍙傛暟1 */
        public int reserved2;       /* 淇濈暀鍙傛暟2 */

        public int sample_rate;     /* 闊抽閲囨牱鐜?*/
        public int channels;        /* 闊抽澹伴亾鏁?*/
        public int bits_per_sample; /* 闊抽閲囨牱绮惧害 */

        public int length;          /* 闊宠棰戝抚澶у皬 */
        public long timestamp_usec; /* 鏃堕棿鎴?寰 */
        public long timestamp_sec;  /* 鏃堕棿鎴?绉?*/

        public long stamp;

        public float bitrate;       /* 姣旂壒鐜?*/
        public float losspacket;    /* 涓㈠寘鐜?*/

        public byte[] buffer;
        public int offset = 0;
        public boolean audio;
    }

    public static final class MediaInfo {
//        Easy_U32 u32VideoCodec;				/* 聽鈥濃垎碌卤鈥÷幝库€♀€撁?*/
//        Easy_U32 u32VideoFps;				/* 聽鈥濃垎碌梅掳卢聽 */
//
//        Easy_U32 u32AudioCodec;				/* 鈥溍欌垎碌卤鈥÷幝库€♀€撁?*/
//        Easy_U32 u32AudioSamplerate;		/* 鈥溍欌垎碌鈮も€︹€斔樎?*/
//        Easy_U32 u32AudioChannel;			/* 鈥溍欌垎碌脮庐碌驴聽藵 */
//        Easy_U32 u32AudioBitsPerSample;		/* 鈥溍欌垎碌鈮も€︹€斔樏β粹垈禄 */
//
//        Easy_U32 u32H264SpsLength;			/* 聽鈥濃垎碌sps梅掳鈮ヂр垈禄 */
//        Easy_U32 u32H264PpsLength;			/* 聽鈥濃垎碌pps梅掳鈮ヂр垈禄 */
//        Easy_U8	 u8H264Sps[128];			/* 聽鈥濃垎碌sps梅掳茠鈦劼烩€?*/
//        Easy_U8	 u8H264Pps[36];				/* 聽鈥濃垎碌sps梅掳茠鈦劼烩€?*/

        int videoCodec;
        int fps;
        int audioCodec;
        int sample;
        int channel;
        int bitPerSample;
        int spsLen;
        int ppsLen;
        byte[] sps;
        byte[] pps;

        @Override
        public String toString() {
            return "MediaInfo{" + "videoCodec=" + videoCodec + ", fps=" + fps + ", audioCodec=" + audioCodec + ", sample=" + sample + ", channel=" + channel + ", bitPerSample=" + bitPerSample + ", spsLen=" + spsLen + ", ppsLen=" + ppsLen + '}';
        }
    }

    public interface SourceCallBack {
        void onSourceCallBack(int _channelId, int _channelPtr, int _frameType, FrameInfo frameInfo);

        void onMediaInfoCallBack(int _channelId, MediaInfo mi);

        void onEvent(int _channelId, int err, int info);

        void sendSeiData(byte[] sei);
    }

    public static final int EASY_SDK_VIDEO_FRAME_FLAG = 0x01;
    public static final int EASY_SDK_AUDIO_FRAME_FLAG = 0x02;
    public static final int EASY_SDK_EVENT_FRAME_FLAG = 0x04;
    public static final int EASY_SDK_RTP_FRAME_FLAG = 0x08;        /* RTP甯ф爣蹇?*/
    public static final int EASY_SDK_SDP_FRAME_FLAG = 0x10;        /* SDP甯ф爣蹇?*/
    public static final int EASY_SDK_MEDIA_INFO_FLAG = 0x20;        /* 濯掍綋绫诲瀷鏍囧織*/
    public static final int EASY_SDK_SEI_FRAME_FLAG = 0x100;        /* SEI甯ф爣蹇?*/


    public static final int EASY_SDK_EVENT_CODEC_ERROR = 0x63657272;    /* ERROR */
    public static final int EASY_SDK_EVENT_CODEC_EXIT = 0x65786974;    /* EXIT */

    public static final int TRANSTYPE_TCP = 1;
    public static final int TRANSTYPE_UDP = 2;

    private static final String TAG = Client.class.getSimpleName();

    static {
        System.loadLibrary("EasyRTSPClient");
    }

    private long mCtx;
    private static final SparseArray<SourceCallBack> sCallbacks = new SparseArray<>();

    Client(Context context) {
        if (context == null) {
            throw new NullPointerException();
        }

        mCtx = init(context, "");
        mContext = context.getApplicationContext();
    }

    int registerCallback(SourceCallBack cb) {
        synchronized (sCallbacks) {
            sCallbacks.put(++sKey, cb);
            return sKey;
        }
    }

    void unrigisterCallback(SourceCallBack cb) {
        synchronized (sCallbacks) {
            int idx = sCallbacks.indexOfValue(cb);
            if (idx != -1) {
                sCallbacks.removeAt(idx);
            }
        }
    }

    public int getLastErrorCode() {
        return getErrorCode(mCtx);
    }

    public int openStream(int channel, String url, int type, int sendOption, int mediaType, String user, String pwd) {
        _channel = channel;
        _url = url;
        _type = type;
        _mediaType = mediaType;
        _user = user;
        _pwd = pwd;
        _sendOption = sendOption;
        return openStream();
    }

    public void closeStream() {
        h.removeCallbacks(closeTask);

        if (mCtx != 0) {
            closeStream(mCtx);
        }
    }

    private static native int getErrorCode(long context);

    private native long init(Context context, String key);

    private native int deInit(long context);

    private int openStream() {
        if (null == _url) {
            throw new NullPointerException();
        }

        if (mCtx == 0) {
            throw new IllegalStateException("init failed: KEY invalid");
        }

        return openStream(mCtx, _channel, _url, _type, _mediaType, _user, _pwd, 1000, 0, _sendOption);
    }

    private native int openStream(long context, int channel, String url, int type, int mediaType, String user, String pwd, int reconn, int outRtpPacket, int rtspOption);

//    private native int startRecord(int context, String path);
//
//    private native void stopRecord(int context);

    private native void closeStream(long context);

    private static void save2path(byte[] buffer, int offset, int length, String path, boolean append) {
        FileOutputStream fos = null;

        try {
            fos = new FileOutputStream(path, append);
            fos.write(buffer, offset, length);
        } catch (FileNotFoundException e) {
            e.printStackTrace();
        } catch (IOException e) {
            e.printStackTrace();
        } finally {
            if (fos != null) {
                try {
                    fos.close();
                } catch (IOException e) {
                    e.printStackTrace();
                }
            }
        }
    }

    private static void onSourceCallBack(int _channelId, int _channelPtr, int _frameType, byte[] pBuf, byte[] frameBuffer) {

        if (false) {
            int permissionCheck = ContextCompat.checkSelfPermission(mContext, Manifest.permission.WRITE_EXTERNAL_STORAGE);
            if (permissionCheck == PackageManager.PERMISSION_GRANTED) {
                // frameType + size + buffer
                if (_frameType != 0) {
                    ByteBuffer bf = ByteBuffer.allocate(5);
                    bf.put((byte) _frameType);
                    if (_frameType == EASY_SDK_MEDIA_INFO_FLAG) {
                        bf.putInt(pBuf.length);
                        save2path(bf.array(), 0, 5, "/sdcard/media_degbu.data", true);
                        save2path(pBuf, 0, pBuf.length, "/sdcard/media_degbu.data", true);
                    } else {
                        bf.putInt(frameBuffer.length);
                        save2path(bf.array(), 0, 5, "/sdcard/media_degbu.data", true);
                        save2path(frameBuffer, 0, frameBuffer.length, "/sdcard/media_degbu.data", true);
                    }
                }
            }
        }


        final SourceCallBack callBack;
        synchronized (sCallbacks) {
            callBack = sCallbacks.get(_channelId);
        }


        if (_frameType == EASY_SDK_SEI_FRAME_FLAG) {
            callBack.sendSeiData(pBuf);
            return;
        }

        if (_frameType == 0) {
            if (callBack != null) {
                callBack.onSourceCallBack(_channelId, _channelPtr, _frameType, null);
            }
            return;
        }

        if (_frameType == EASY_SDK_MEDIA_INFO_FLAG) {
            if (callBack != null) {
                MediaInfo mi = new MediaInfo();

                ByteBuffer buffer = ByteBuffer.wrap(pBuf);
                buffer.order(ByteOrder.LITTLE_ENDIAN);
                mi.videoCodec = buffer.getInt();
                mi.fps = buffer.getInt();
                mi.audioCodec = buffer.getInt();
                mi.sample = buffer.getInt();
                mi.channel = buffer.getInt();
                mi.bitPerSample = buffer.getInt();
                mi.spsLen = buffer.getInt();
                mi.ppsLen = buffer.getInt();
                mi.sps = new byte[128];
                mi.pps = new byte[36];

                buffer.get(mi.sps);
                buffer.get(mi.pps);
//                    int videoCodec;int fps;
//                    int audioCodec;int sample;int channel;int bitPerSample;
//                    int spsLen;
//                    int ppsLen;
//                    byte[]sps;
//                    byte[]pps;

                callBack.onMediaInfoCallBack(_channelId, mi);
            }
            return;
        }

        ByteBuffer buffer = ByteBuffer.wrap(frameBuffer);
        buffer.order(ByteOrder.LITTLE_ENDIAN);
        FrameInfo fi = new FrameInfo();
        fi.codec = buffer.getInt();
        fi.type = buffer.getInt();
        fi.fps = buffer.get();
        buffer.get();
        fi.width = buffer.getShort();
        fi.height = buffer.getShort();
        buffer.getInt();
        buffer.getInt();
        buffer.getShort();
        fi.sample_rate = buffer.getInt();
        fi.channels = buffer.getInt();
        fi.bits_per_sample = buffer.getInt();
        fi.length = buffer.getInt();
        fi.timestamp_usec = buffer.getInt();
        fi.timestamp_sec = buffer.getInt();

        long sec = fi.timestamp_sec < 0 ? Integer.MAX_VALUE - Integer.MIN_VALUE + 1 + fi.timestamp_sec : fi.timestamp_sec;
        long usec = fi.timestamp_usec < 0 ? Integer.MAX_VALUE - Integer.MIN_VALUE + 1 + fi.timestamp_usec : fi.timestamp_usec;
        fi.stamp = sec * 1000000 + usec;

//        long differ = fi.stamp - mPreviewStamp;
//        Log.d(TAG, String.format("%s:%d,%d,%d, %d", EASY_SDK_VIDEO_FRAME_FLAG == _frameType ? "瑙嗛" : "闊抽", fi.stamp, fi.timestamp_sec, fi.timestamp_usec, differ));
        fi.buffer = pBuf;

        boolean paused = false;
        synchronized (_channelPause) {
            paused = _channelPause.contains(_channelId);
        }

        if (callBack != null) {
            if (paused) {
                Log.i(TAG, "channel_" + _channelId + " is paused!");
            }
            callBack.onSourceCallBack(_channelId, _channelPtr, _frameType, fi);
        }
    }



    private static void onEvent(int channel, int err, int state) {
        // state锛? Connecting, 2 杩炴帴閿欒, 3 杩炴帴绾跨▼閫€鍑?
        // err鐨勫惈涔夛細http璇锋眰鐨勮繑鍥炵爜锛?00锛?00锛?01绛夌瓑锛?
        Log.e(TAG, String.format("__RTSPClientCallBack onEvent: err=%d, state=%d", err, state));

        synchronized (sCallbacks) {
            final SourceCallBack callBack = sCallbacks.get(channel);
            if (callBack != null) {
                callBack.onEvent(channel, err, state);
            }
        }
    }

    public void pause() {
        if (Looper.myLooper() != Looper.getMainLooper()) {
            throw new IllegalThreadStateException("please call pause in Main thread!");
        }

        synchronized (_channelPause) {
            _channelPause.add(_channel);
        }

        paused = 1;
        Log.i(TAG, "pause:=" + 1);
        h.postDelayed(closeTask, 10000);
    }

    public void resume() {
        if (Looper.myLooper() != Looper.getMainLooper()) {
            throw new IllegalThreadStateException("call resume in Main thread!");
        }

        synchronized (_channelPause) {
            _channelPause.remove(_channel);
        }

        h.removeCallbacks(closeTask);

        if (paused == 2) {
            Log.i(TAG, "resume:=" + 0);
            openStream();
        }

        Log.i(TAG, "resume:=" + 0);
        paused = 0;
    }

    @Override
    public void close() throws IOException {
        h.removeCallbacks(closeTask);
        _channelPause.remove(_channel);

        if (mCtx == 0) throw new IOException("not opened or already closed");

        deInit(mCtx);
        mCtx = 0;
    }
}
