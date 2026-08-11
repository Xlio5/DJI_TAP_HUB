package com.tunnathub.app.video;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.util.Log;

import com.tunnathub.app.BuildConfig;

public final class RtspUdpProbeReceiver extends BroadcastReceiver {
    public static final String ACTION = "com.tunnathub.app.RTSP_UDP_PROBE";
    private static final String TAG = "RtspUdpProbe";

    @Override
    public void onReceive(Context context, Intent intent) {
        if (intent == null || !ACTION.equals(intent.getAction())) return;
        if (!BuildConfig.DEBUG) return;
        final PendingResult pending = goAsync();
        final Context appContext = context.getApplicationContext();
        final String url = resolveUrl(appContext, intent);
        new Thread(() -> {
            try {
                Log.i(TAG, "adb start " + url);
                RtspUdpProbe.Result normal = RtspUdpProbe.run(url, 5);
                RtspUdpProbe.Result protectedTun = RtspUdpProbe.runProtectedTun(url, 5);
                String text = normal.toDisplayString() + "\n\n" + protectedTun.toDisplayString();
                Log.i(TAG, text);
            } finally {
                pending.finish();
            }
        }, "RTSP_UDP_PROBE_ADB").start();
    }

    private static String resolveUrl(Context context, Intent intent) {
        String extra = intent.getStringExtra("url");
        if (extra != null && !extra.isBlank()) return extra;
        SharedPreferences prefs = context.getSharedPreferences("tun_nat_hub", Context.MODE_PRIVATE);
        String saved = prefs.getString("rtsp_url", null);
        return saved == null || saved.isBlank() ? "rtsp://192.168.144.31:554/stream1" : saved;
    }
}
