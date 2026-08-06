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
import androidx.compose.runtime.*
import androidx.compose.ui.platform.LocalContext
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme

class LuaParamActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val host = intent.getStringExtra("host") ?: "192.168.144.66"
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
    val controller = remember { LuaParamController(ctx) }
    var rows by remember { mutableStateOf<List<ParamRow>>(emptyList()) }

    // 订阅控制器行变化
    DisposableEffect(controller) {
        controller.onRowsChanged = { rows = controller.getRows() }
        controller.start(host)
        onDispose {
            controller.onRowsChanged = null
            controller.stop()
        }
    }

    LuaParamScreen(
        rows = rows,
        onUp = { controller.up() },
        onDown = { controller.down() },
        onEnter = { controller.enter() },
        onExit = { controller.exit() },
        onReload = { controller.reload() }
    )
}
