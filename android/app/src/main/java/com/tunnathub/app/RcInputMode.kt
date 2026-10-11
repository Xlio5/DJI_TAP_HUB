package com.tunnathub.app

import android.content.Context

private const val RC_CHANNEL_COUNT = 16

/** App 侧 RC 输入源选择。 */
enum class RcInputMode(val prefValue: String, val label: String) {
    ANDROID_FUSION("android_fusion", "安卓融合"),
    V3S_SERIAL("v3s_serial", "V3s 串口"),
    V3S_ADB("v3s_adb", "V3s ADB");

    val usesAndroidFusion: Boolean get() = this == ANDROID_FUSION
    val usesV3sRcMsg: Boolean get() = this != ANDROID_FUSION

    companion object {
        const val PREFS_NAME = "tun_nat_hub"
        const val PREF_KEY = "rc_input_mode"

        fun fromPref(value: String?): RcInputMode = when (value) {
            "v3s_rcmsg" -> V3S_SERIAL
            else -> values().firstOrNull { it.prefValue == value } ?: ANDROID_FUSION
        }

        fun fromPreferences(context: Context): RcInputMode =
            fromPref(context.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE).getString(PREF_KEY, null))
    }
}

fun rcChannelsForIncomingData(
    current: List<Int>,
    incoming: List<Int>,
    inputMode: RcInputMode,
    source: String
): List<Int> {
    if (incoming.size != RC_CHANNEL_COUNT || current.size != RC_CHANNEL_COUNT) return incoming
    return when {
        inputMode.usesV3sRcMsg && source == "V3S-RCMSG" -> incoming
        source == "RC-FUSION" -> incoming.take(6) + current.drop(6)
        source == "V3S-RCMSG" -> current.take(6) + incoming.drop(6)
        else -> incoming
    }
}

fun rcChannelsForIncomingDataForTest(
    current: List<Int>,
    incoming: List<Int>,
    inputMode: RcInputMode,
    source: String
): List<Int> = rcChannelsForIncomingData(current, incoming, inputMode, source)

fun rcTopStatusText(
    connected: Boolean,
    inputMode: RcInputMode,
    rcType: String,
    geteventHz: Float,
    p40007Hz: Float,
    v3sGood1Hz: Float,
    v3sGood2Hz: Float,
    v3sRcMsgHz: Float
): String {
    if (!connected) return "等待 dji_rc 数据"
    return when (inputMode) {
        RcInputMode.V3S_SERIAL ->
            "dji_rc online $rcType  921600 ${formatRcHz(v3sGood1Hz)} · 115200 ${formatRcHz(v3sGood2Hz)} · rcmsg ${formatRcHz(v3sRcMsgHz)}"
        RcInputMode.V3S_ADB ->
            "dji_rc online $rcType  V3s ADB · rcmsg ${formatRcHz(v3sRcMsgHz)}"
        RcInputMode.ANDROID_FUSION ->
            "dji_rc online $rcType  getevent ${formatRcHz(geteventHz)} · 40007 ${formatRcHz(p40007Hz)}"
    }
}

private fun formatRcHz(hz: Float): String =
    if (hz > 0.05f) if (hz >= 1f) "%.0fHz".format(hz) else "%.1fHz".format(hz) else "—Hz"

fun rcTopStatusTextForTest(
    connected: Boolean,
    inputMode: RcInputMode,
    rcType: String,
    geteventHz: Float,
    p40007Hz: Float,
    v3sGood1Hz: Float,
    v3sGood2Hz: Float,
    v3sRcMsgHz: Float
): String = rcTopStatusText(connected, inputMode, rcType, geteventHz, p40007Hz, v3sGood1Hz, v3sGood2Hz, v3sRcMsgHz)
