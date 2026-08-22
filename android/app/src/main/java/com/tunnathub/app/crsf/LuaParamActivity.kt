/**
 * LuaParamActivity.kt — ELRS 参数配置页 (独立 Activity)
 *
 * 从 MainActivity 的 CONFIG 页进入。连接 V3s crsf-bridge,
 * 跑 elrsV3.lua 渲染参数界面, 上下选择 + 确认操作参数。
 */
package com.tunnathub.app.crsf

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import android.util.Log
import androidx.compose.runtime.*
import androidx.compose.ui.platform.LocalContext
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import kotlinx.coroutines.delay

class LuaParamActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        // 优先 intent 传 host; 默认 10.0.2.2 (Android 模拟器→宿主机 NAT 网关)
        val host = intent.getStringExtra("host") ?: "10.0.2.2"
        setContent {
            MaterialTheme(colorScheme = darkColorScheme()) {
                LuaParamPage(host)
            }
        }
    }
}

@Composable
private fun LuaParamPage(host: String) {
    val ctx = LocalContext.current
    val activity = ctx as? ComponentActivity
    val controller = remember { LuaParamController(ctx) }
    var rows by remember { mutableStateOf<List<ParamRow>>(emptyList()) }
    var title by remember { mutableStateOf("ELRS") }
    var loading by remember { mutableStateOf(true) }
    var phase by remember { mutableStateOf("连接 V3s...") }

    // 加载进度条至少显示 800ms, 避免参数加载过快一闪而过
    LaunchedEffect(Unit) {
        delay(800)
        if (!controller.isLoading) loading = false
    }

    // 订阅控制器行变化 (rebuildRows 可能在后台线程, 切主线程更新 Compose)
    DisposableEffect(controller) {
        controller.onRowsChanged = {
            val newRows = controller.getRows()
            if (activity != null) {
                activity.runOnUiThread { rows = newRows }
            } else {
                rows = newRows
            }
        }
        controller.onTitleChanged = {
            if (activity != null) activity.runOnUiThread { title = it }
            else title = it
        }
        controller.onLoadingChanged = { isLoading ->
            if (activity != null) activity.runOnUiThread { loading = isLoading }
            else loading = isLoading
        }
        controller.onPhaseChanged = { text ->
            if (activity != null) activity.runOnUiThread { phase = text }
            else phase = text
        }
        controller.start(host)
        onDispose {
            controller.onRowsChanged = null
            controller.onTitleChanged = null
            controller.onLoadingChanged = null
            controller.onPhaseChanged = null
            controller.stop()
        }
    }

    LuaParamScreen(
        rows = rows,
        title = title,
        isLoading = loading,
        loadingPhase = phase,
        onUp = { controller.up() },
        onDown = { controller.down() },
        onEnter = { controller.enter() },
        onExit = { controller.exit() },
        onReload = { controller.reload() }
    )
}
