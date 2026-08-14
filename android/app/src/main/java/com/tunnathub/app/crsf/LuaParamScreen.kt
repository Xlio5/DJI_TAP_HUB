/**
 * LuaParamScreen.kt — ELRS 参数配置界面 (Lua 引擎驱动)
 *
 * 用 LuaEngine 跑 elrsV3.lua, 把 lcd.drawText 的行渲染成列表,
 * 用户上下选择 + 确认/取消 → event() 回调 Lua 脚本。
 * 布局: 左侧参数列表(选中行▶箭头), 右侧操作按钮(上/下/确认/返回)。
 */
package com.tunnathub.app.crsf

import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** Lua 渲染的参数行 (由 LuaEngine.onLine 填充) */
data class ParamRow(val text: String, val selected: Boolean, val editing: Boolean = false)

@Composable
fun LuaParamScreen(
    rows: List<ParamRow>,
    onUp: () -> Unit,
    onDown: () -> Unit,
    onEnter: () -> Unit,
    onExit: () -> Unit,
    onReload: () -> Unit,
    title: String = "ELRS"
) {
    Row(Modifier.fillMaxSize().padding(8.dp)) {
        // ── 左侧: 标题 + 参数列表 ──
        Column(Modifier.weight(1f).fillMaxHeight()) {
            // 标题栏 + 刷新
            Row(Modifier.fillMaxWidth().padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                Text(title.ifEmpty { "ELRS" }, style = MaterialTheme.typography.titleMedium, modifier = Modifier.weight(1f))
                TextButton(onClick = onReload) { Text("刷新") }
            }

            // 参数列表
            if (rows.isEmpty()) {
                Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                    Text("无参数 (连接 V3s + ELRS 模块后刷新)")
                }
            } else {
                LazyColumn(Modifier.weight(1f)) {
                    itemsIndexed(rows) { idx, row ->
                        // 编辑中(BLINK)闪烁提醒: 用无限动画交替高亮背景
                        val blinkAlpha = if (row.editing) {
                            val t = rememberInfiniteTransition()
                            val a by t.animateFloat(
                                initialValue = 1f, targetValue = 0.25f,
                                animationSpec = infiniteRepeatable(tween(400), RepeatMode.Reverse),
                                label = "blink"
                            )
                            a
                        } else 1f
                        val bg = when {
                            row.editing -> Color(0xBB47C9FF).copy(alpha = blinkAlpha)
                            row.selected -> Color(0x3347C9FF)
                            else -> Color.Transparent
                        }
                        Row(
                            Modifier
                                .fillMaxWidth()
                                .background(bg)
                                .clickable { /* 预留点击选中 */ }
                                .padding(horizontal = 12.dp, vertical = 8.dp),
                            verticalAlignment = Alignment.CenterVertically
                        ) {
                            if (row.selected) {
                                Text("▶ ", color = Color(0xFF38BDF8), fontWeight = FontWeight.Bold, fontSize = 18.sp)
                            } else {
                                Text("  ", fontSize = 18.sp)
                            }
                            Text(
                                row.text,
                                fontSize = 16.sp,
                                fontWeight = if (row.selected) FontWeight.Bold else FontWeight.Normal,
                                color = if (row.selected) Color(0xFF7DD3FC) else Color.Unspecified
                            )
                        }
                    }
                }
            }
        }

        // ── 右侧: 操作按钮列 (上下/确认/返回) ──
        Column(
            Modifier.width(72.dp).fillMaxHeight().padding(start = 6.dp),
            verticalArrangement = Arrangement.Center,
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            FilledTonalButton(
                onClick = onUp,
                modifier = Modifier.fillMaxWidth().height(44.dp).padding(bottom = 6.dp)
            ) { Text("▲", fontSize = 16.sp) }
            FilledTonalButton(
                onClick = onDown,
                modifier = Modifier.fillMaxWidth().height(44.dp).padding(bottom = 6.dp)
            ) { Text("▼", fontSize = 16.sp) }
            Button(
                onClick = onEnter,
                colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF0EA5E9)),
                modifier = Modifier.fillMaxWidth().height(44.dp).padding(bottom = 6.dp)
            ) { Text("确认", fontSize = 13.sp) }
            TextButton(onClick = onExit, modifier = Modifier.fillMaxWidth()) { Text("返回", fontSize = 13.sp) }
        }
    }
}
