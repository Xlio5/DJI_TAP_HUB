/**
 * LuaParamScreen.kt — ELRS 参数配置界面 (Lua 引擎驱动)
 *
 * 用 LuaEngine 跑 elrsV3.lua, 把 lcd.drawText 的行渲染成列表,
 * 用户上下选择 + 确认/取消 → event() 回调 Lua 脚本。
 * 布局: 左侧参数列表(选中行▶箭头), 右侧操作按钮(上/下/确认/返回)。
 * 美化: 深色渐变背景 + 连接状态点 + 加载进度条 + 卡片化参数行。
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
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

/** Lua 渲染的参数行 (由 LuaEngine.onLine 填充) */
data class ParamRow(val text: String, val selected: Boolean, val editing: Boolean = false)

@Composable
fun LuaParamScreen(
    rows: List<ParamRow>,
    isLoading: Boolean = false,
    loadingPhase: String = "",
    popupText: String = "",
    onUp: () -> Unit,
    onDown: () -> Unit,
    onEnter: () -> Unit,
    onExit: () -> Unit,
    onReload: () -> Unit,
    title: String = "ELRS"
) {
    // 深色渐变背景 (无人机/遥控器深色主题)
    Box(
        Modifier
            .fillMaxSize()
            .background(Brush.verticalGradient(listOf(Color(0xFF0B1220), Color(0xFF16233B))))
    ) {
        Row(Modifier.fillMaxSize().padding(10.dp)) {
            // ── 左侧: 标题 + 进度 + 参数列表 ──
            Column(Modifier.weight(1f).fillMaxHeight()) {
                // 标题栏: 连接状态点 + 设备名 + 刷新
                Row(
                    Modifier.fillMaxWidth().padding(vertical = 6.dp),
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    // 连接状态点: 加载=黄, 就绪=绿
                    val dotColor = if (isLoading) Color(0xFFF59E0B) else Color(0xFF22C55E)
                    Box(Modifier.size(10.dp).background(dotColor, CircleShape))
                    Spacer(Modifier.width(8.dp))
                    Text(
                        title.ifEmpty { "ELRS" },
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold,
                        color = Color(0xFFF8FAFC),
                        modifier = Modifier.weight(1f)
                    )
                    TextButton(onClick = onReload) {
                        Text("刷新", color = Color(0xFF7DD3FC))
                    }
                }

                // ── Bind/命令弹出提示 (popupConfirmation) ──
                if (popupText.isNotEmpty()) {
                    Text(
                        "▶ $popupText",
                        color = Color(0xFFF59E0B),
                        fontWeight = FontWeight.Bold,
                        fontSize = 13.sp,
                        modifier = Modifier.padding(horizontal = 4.dp, vertical = 2.dp)
                    )
                }

                // ── 加载进度条 (连接 V3s / 加载脚本 / 等待 ELRS) ──
                if (isLoading) {
                    LinearProgressIndicator(
                        modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp),
                        color = Color(0xFF38BDF8),
                        trackColor = Color(0xFF1E3A5F)
                    )
                    Text(
                        loadingPhase.ifEmpty { "加载中..." },
                        fontSize = 12.sp,
                        color = Color(0xFF94A3B8),
                        modifier = Modifier.padding(bottom = 4.dp)
                    )
                }

                // ── 参数列表 ──
                if (!isLoading && rows.isEmpty()) {
                    Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        Text("无参数 (连接 V3s + ELRS 模块后刷新)", color = Color(0xFF64748B))
                    }
                } else if (rows.isNotEmpty()) {
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
                                row.editing -> Color(0xBB38BDF8).copy(alpha = blinkAlpha)
                                row.selected -> Color(0x4038BDF8)
                                else -> Color(0x0D0F172A)
                            }
                            Row(
                                Modifier
                                    .fillMaxWidth()
                                    .padding(vertical = 3.dp)
                                    .background(bg, RoundedCornerShape(8.dp))
                                    .clickable { /* 预留点击选中 */ }
                                    .padding(horizontal = 14.dp, vertical = 10.dp),
                                verticalAlignment = Alignment.CenterVertically
                            ) {
                                // 选中标记 ▶
                                if (row.selected) {
                                    Text(
                                        "▶",
                                        color = Color(0xFF38BDF8),
                                        fontWeight = FontWeight.Bold,
                                        fontSize = 15.sp,
                                        modifier = Modifier.width(22.dp)
                                    )
                                } else {
                                    Spacer(Modifier.width(22.dp))
                                }
                                Text(
                                    row.text,
                                    fontSize = 16.sp,
                                    fontWeight = if (row.selected) FontWeight.SemiBold else FontWeight.Normal,
                                    color = if (row.selected) Color(0xFFE0F2FE) else Color(0xFFCBD5E1)
                                )
                            }
                        }
                    }
                }
            }

            // ── 右侧: 操作按钮列 (上/下/确认/返回) ──
            Column(
                Modifier.width(76.dp).fillMaxHeight().padding(start = 8.dp),
                verticalArrangement = Arrangement.Center,
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                FilledTonalButton(
                    onClick = onUp,
                    modifier = Modifier.fillMaxWidth().height(48.dp).padding(bottom = 8.dp),
                    shape = RoundedCornerShape(10.dp)
                ) { Text("▲", fontSize = 16.sp) }
                FilledTonalButton(
                    onClick = onDown,
                    modifier = Modifier.fillMaxWidth().height(48.dp).padding(bottom = 8.dp),
                    shape = RoundedCornerShape(10.dp)
                ) { Text("▼", fontSize = 16.sp) }
                Button(
                    onClick = onEnter,
                    colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF0EA5E9)),
                    modifier = Modifier.fillMaxWidth().height(48.dp).padding(bottom = 8.dp),
                    shape = RoundedCornerShape(10.dp)
                ) { Text("确认", fontSize = 13.sp, fontWeight = FontWeight.Bold) }
                TextButton(onClick = onExit, modifier = Modifier.fillMaxWidth()) {
                    Text("返回", fontSize = 13.sp, color = Color(0xFF94A3B8))
                }
            }
        }
    }
}
