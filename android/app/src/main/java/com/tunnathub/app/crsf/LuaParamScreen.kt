/**
 * LuaParamScreen.kt — ELRS 参数配置界面 (Lua 引擎驱动)
 *
 * 用 LuaEngine 跑 elrsV3.lua, 把 lcd.drawText 的行渲染成列表,
 * 用户上下选择 + 确认/取消 → event() 回调 Lua 脚本。
 */
package com.tunnathub.app.crsf

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** Lua 渲染的参数行 (由 LuaEngine.onLine 填充) */
data class ParamRow(val text: String, val selected: Boolean)

@Composable
fun LuaParamScreen(
    rows: List<ParamRow>,
    onUp: () -> Unit,
    onDown: () -> Unit,
    onEnter: () -> Unit,
    onExit: () -> Unit,
    onReload: () -> Unit
) {
    Column(Modifier.fillMaxSize().padding(8.dp)) {
        // 标题栏 + 操作按钮
        Row(Modifier.fillMaxWidth().padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
            Text("ELRS 参数", style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
            TextButton(onClick = onReload) { Text("刷新") }
            TextButton(onClick = onExit) { Text("退出") }
        }

        // Lua 渲染的参数列表
        if (rows.isEmpty()) {
            Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                Text("无参数 (连接 V3s + ELRS 模块后刷新)")
            }
        } else {
            LazyColumn(Modifier.weight(1f)) {
                itemsIndexed(rows) { idx, row ->
                    val bg = if (row.selected) Color(0x33FFFFFF) else Color.Transparent
                    Row(
                        Modifier.fillMaxWidth().background(bg).padding(horizontal = 12.dp, vertical = 8.dp),
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        if (row.selected) {
                            Text("▶ ", color = MaterialTheme.colorScheme.primary)
                        }
                        Text(row.text, fontSize = 16.sp)
                    }
                }
            }
        }

        // 底部操作提示
        Row(Modifier.fillMaxWidth().padding(vertical = 4.dp), horizontalArrangement = Arrangement.SpaceEvenly) {
            TextButton(onClick = onUp) { Text("▲ 上") }
            TextButton(onClick = onEnter) { Text("确认") }
            TextButton(onClick = onDown) { Text("▼ 下") }
        }
    }
}
