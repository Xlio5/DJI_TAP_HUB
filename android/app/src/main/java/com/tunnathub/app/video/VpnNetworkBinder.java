package com.tunnathub.app.video;

import android.content.Context;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.NetworkCapabilities;
import android.util.Log;

public final class VpnNetworkBinder {
    private static final String TAG = "VpnNetworkBinder";
    private static int sBindCount;

    private VpnNetworkBinder() {}

    public static synchronized boolean bindProcessToVpn(Context context) {
        Network network = findVpnNetwork(context);
        if (network == null) {
            Log.w(TAG, "VPN network not found");
            return false;
        }
        ConnectivityManager cm = (ConnectivityManager) context.getApplicationContext()
                .getSystemService(Context.CONNECTIVITY_SERVICE);
        if (cm == null) return false;
        boolean ok = cm.bindProcessToNetwork(network);
        if (ok) sBindCount++;
        Log.i(TAG, "bindProcessToVpn " + network + " ok=" + ok + " count=" + sBindCount);
        return ok;
    }

    private static Network findVpnNetwork(Context context) {
        ConnectivityManager cm = (ConnectivityManager) context.getApplicationContext()
                .getSystemService(Context.CONNECTIVITY_SERVICE);
        if (cm == null) return null;
        for (Network network : cm.getAllNetworks()) {
            NetworkCapabilities caps = cm.getNetworkCapabilities(network);
            if (caps != null && caps.hasTransport(NetworkCapabilities.TRANSPORT_VPN)) {
                return network;
            }
        }
        return null;
    }

    public static synchronized void clearProcessBinding(Context context) {
        if (sBindCount <= 0) return;
        sBindCount--;
        if (sBindCount > 0) {
            Log.i(TAG, "clearProcessBinding deferred count=" + sBindCount);
            return;
        }
        ConnectivityManager cm = (ConnectivityManager) context.getApplicationContext()
                .getSystemService(Context.CONNECTIVITY_SERVICE);
        if (cm != null) {
            cm.bindProcessToNetwork(null);
            Log.i(TAG, "clearProcessBinding count=0");
        }
    }
}
