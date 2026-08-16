/**
 * UdpToolPage.kt — 特殊调试版 UDP 工具页
 *
 * 用途: 局域网 UDP 收发测试 (老大要求特殊版才带, 正常版无此页)。
 * 复用 TunNatVpnService.openProtectedPort(port) — 绑定手机局域网 IP (192.168.144.11)
 * + DatagramChannel.open(INET) 纯 IPv4 socket, 能收到经 tun0 进来的隧道 IPv4 包。
 *
 * 功能:
 *   - 监听端口: 输入端口 → 启动监听 → 电脑发 144.11:端口 的数据在此显示
 *   - 发送: 填目标 IP + 端口 + 数据 → 发送到局域网
 */

package com.tunnathub.app

import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.layout.RowScope
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.tunnathub.app.service.TunNatVpnService
import com.tunnathub.app.util.AppLog
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetSocketAddress

@Composable
fun UdpToolPage() {
    var listenPort by remember { mutableStateOf("14550") }
    var listening by remember { mutableStateOf(false) }
    var targetIp by remember { mutableStateOf("192.168.144.88") }
    var targetPort by remember { mutableStateOf("14550") }
    var sendData by remember { mutableStateOf("") }
    var stressCount by remember { mutableStateOf("600000") }
    var stressing by remember { mutableStateOf(false) }
    var logLines by remember { mutableStateOf(listOf<String>()) }
    val scope = rememberCoroutineScope()

    // 监听 socket (持引用, 页面离开时关闭)
    var recvSock by remember { mutableStateOf<DatagramSocket?>(null) }
    // 监听循环控制: 用 AtomicBoolean 而非 Compose state (避免 IO 协程读快照问题)
    val runFlag = remember { java.util.concurrent.atomic.AtomicBoolean(false) }
    // 监听端口记录 (供 DisposableEffect 清理用)
    var activePort by remember { mutableStateOf<Int?>(null) }

    // 页面离开时清理: 停协程 + 释放端口 + 关 socket
    androidx.compose.runtime.DisposableEffect(Unit) {
        onDispose {
            runFlag.set(false)
            activePort?.let { TunNatVpnService.releasePort(it) }
            recvSock?.close()
            recvSock = null
        }
    }

    fun addLog(line: String) {
        logLines = (logLines + "[${timeNow()}] $line").takeLast(200)
    }

    Column(modifier = Modifier.fillMaxSize().background(Color(0xFF0F172A)).verticalScroll(rememberScrollState()).padding(16.dp)) {
        Text("UDP 工具 (特殊调试版)", fontSize = 15.sp, color = Color(0xFF38BDF8), fontWeight = androidx.compose.ui.text.font.FontWeight.Bold)
        Text("局域网 UDP 收发 · 手机 IP = ${TunNatVpnService.currentLanAddr} · 电脑发此 IP:端口", fontSize = 9.sp, color = Color(0xFF64748B))

        Spacer(Modifier.height(12.dp))

        // ── 监听区 ──
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
            Text("监听端口", fontSize = 11.sp, color = Color(0xFF94A3B8), modifier = Modifier.width(70.dp))
            Field(listenPort) { listenPort = it }
            Spacer(Modifier.width(8.dp))
            Button(onClick = {
                val port = listenPort.filter { it.isDigit() }.toIntOrNull()
                if (port == null || port < 1 || port > 65535) { addLog("端口无效"); return@Button }
                if (!listening) {
                    // 先释放旧端口 (避免 openProtectedPort 复用失效 socket, 协程与 socket 脱节)
                    TunNatVpnService.releasePort(port)
                    // 绑内部转发地址 10.0.0.2 + VPN 网络: V3s 把电脑发的 144.11:port DNAT 到此
                    // (openVpnBoundPort 用 bindSocketToVpn 而非 protect, 才能收电脑转发的包)
                    val sock = TunNatVpnService.openVpnBoundPort(port)
                    if (sock == null) { addLog("监听失败: 无法打开端口 $port (VPN 未连接?)"); return@Button }
                    sock.soTimeout = 500
                    recvSock = sock
                    activePort = port
                    runFlag.set(true)
                    listening = true
                    addLog("开始监听 10.0.0.2:$port (电脑发 192.168.144.11:$port, V3s DNAT 到此)")
                    scope.launch(Dispatchers.IO) {
                        val buf = ByteArray(2048)
                        val mySock = sock
                        AppLog.i("UdpTool", "监听线程启动 runFlag=$runFlag sock=$mySock")
                        var loopCount = 0
                        // 批量更新 UI: IO 协程只累积日志到本地队列, 每 100ms 切主线程刷一次
                        // (避免每包 withContext(Main) 成为吞吐瓶颈, 压测丢包根因)
                        val pendingLog = java.util.concurrent.ConcurrentLinkedQueue<String>()
                        var lastFlush = System.currentTimeMillis()
                        suspend fun flushToUi() {
                            val batch = java.util.ArrayList<String>()
                            while (true) { val s = pendingLog.poll() ?: break; batch.add(s) }
                            if (batch.isEmpty()) return
                            kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.Main) {
                                logLines = (logLines + batch).takeLast(2000)
                            }
                        }
                        while (runFlag.get()) {
                            try {
                                val pkt = DatagramPacket(buf, buf.size)
                                mySock.receive(pkt)
                                val data = pkt.data.copyOf(pkt.length)
                                val hex = data.take(32).joinToString(" ") { "%02x".format(it) }
                                val ascii = String(data, Charsets.UTF_8).replace(Regex("[^\\x20-\\x7E]"), ".")
                                val line1 = "RX ${pkt.length}B from ${pkt.address?.hostAddress}:${pkt.port} [$hex]"
                                val line2 = if (ascii.isNotBlank()) "   ASCII: $ascii" else null
                                pendingLog.add("${timeNow()} $line1")
                                if (line2 != null) pendingLog.add("${timeNow()} $line2")
                                if (System.currentTimeMillis() - lastFlush >= 100) {
                                    flushToUi()
                                    lastFlush = System.currentTimeMillis()
                                }
                            } catch (_: java.net.SocketTimeoutException) {
                                loopCount++
                                if (System.currentTimeMillis() - lastFlush >= 100) {
                                    flushToUi()
                                    lastFlush = System.currentTimeMillis()
                                }
                                if (loopCount % 40 == 0) AppLog.i("UdpTool", "循环等待 ${loopCount} 次")
                            } catch (e: Exception) {
                                AppLog.i("UdpTool", "RX 异常: ${e.message}")
                                flushToUi()
                                if (runFlag.get()) {
                                    kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.Main) {
                                        logLines = (logLines + "[${timeNow()}] RX err: ${e.message}").takeLast(2000)
                                    }
                                }
                                break
                            }
                        }
                        flushToUi()
                    }
                } else {
                    runFlag.set(false)
                    listening = false
                    activePort = null
                    TunNatVpnService.releasePort(port)
                    recvSock?.close()
                    recvSock = null
                    addLog("停止监听")
                }
            }, modifier = Modifier.height(32.dp), colors = ButtonDefaults.buttonColors(containerColor = if (listening) Color(0xFFDC2626) else Color(0xFF2563EB)),
                contentPadding = PaddingValues(horizontal = 12.dp, vertical = 0.dp)) {
                Text(if (listening) "停止" else "监听", fontSize = 11.sp)
            }
        }
        if (listening) Text("● 监听中 (日志 ${logLines.size} 条)", fontSize = 10.sp, color = Color(0xFF22C55E), modifier = Modifier.padding(top = 2.dp))

        Spacer(Modifier.height(16.dp))

        // ── 发送区 ──
        Text("发送 UDP", fontSize = 12.sp, color = Color(0xFFE2E8F0), fontWeight = androidx.compose.ui.text.font.FontWeight.Bold)
        Spacer(Modifier.height(6.dp))
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
            Text("目标IP", fontSize = 11.sp, color = Color(0xFF94A3B8), modifier = Modifier.width(70.dp))
            Field(targetIp) { targetIp = it }
        }
        Spacer(Modifier.height(4.dp))
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
            Text("目标端口", fontSize = 11.sp, color = Color(0xFF94A3B8), modifier = Modifier.width(70.dp))
            Field(targetPort) { targetPort = it }
        }
        Spacer(Modifier.height(4.dp))
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
            Text("数据", fontSize = 11.sp, color = Color(0xFF94A3B8), modifier = Modifier.width(70.dp))
            Field(sendData) { sendData = it }
        }
        Spacer(Modifier.height(6.dp))
        Button(onClick = {
            val port = targetPort.filter { it.isDigit() }.toIntOrNull()
            if (port == null || targetIp.isBlank() || sendData.isBlank()) { addLog("目标/端口/数据不能为空"); return@Button }
            scope.launch(Dispatchers.IO) {
                try {
                    // 走 tun0 隧道: openVpnBoundPort(0) = bind 10.0.0.2:随机 + bindSocketToVpn
                    // (普通 DatagramSocket bind 144.11 会命中 fwmark0→wlan0 策略路由, 到不了电脑)
                    val sock = TunNatVpnService.openVpnBoundPort(0)
                    if (sock == null) { addLog("发送失败: VPN 未连接"); return@launch }
                    val pkt = DatagramPacket(sendData.toByteArray(), sendData.toByteArray().size,
                        java.net.InetAddress.getByName(targetIp), port)
                    sock.send(pkt)
                    sock.close()
                    addLog("TX → $targetIp:$port: $sendData")
                } catch (e: Exception) {
                    addLog("TX err: ${e.message}")
                }
            }
        }, modifier = Modifier.height(32.dp), colors = ButtonDefaults.buttonColors(containerColor = Color(0xFF059669)),
            contentPadding = PaddingValues(horizontal = 12.dp, vertical = 0.dp)) { Text("发送", fontSize = 11.sp) }

        Spacer(Modifier.height(6.dp))
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.fillMaxWidth()) {
            Text("压测包数", fontSize = 11.sp, color = Color(0xFF94A3B8), modifier = Modifier.width(70.dp))
            Field(stressCount) { stressCount = it }
        }
        Spacer(Modifier.height(6.dp))
        // 压测发送: 500B/1ms × N 包, 走 tun0 隧道 (openVpnBoundPort(0) = bind 10.0.0.2 + bindSocketToVpn)
        Button(onClick = {
            val port = targetPort.filter { it.isDigit() }.toIntOrNull()
            val count = stressCount.filter { it.isDigit() }.toLongOrNull()
            if (port == null || targetIp.isBlank() || count == null || count < 1) { addLog("目标/端口/包数无效"); return@Button }
            if (stressing) { addLog("压测发送进行中, 请等待"); return@Button }
            stressing = true
            scope.launch(Dispatchers.IO) {
                var sent = 0L
                suspend fun uiLog(line: String) {
                    kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.Main) {
                        logLines = (logLines + "[${timeNow()}] $line").takeLast(2000)
                    }
                }
                try {
                    val sock = TunNatVpnService.openVpnBoundPort(0)
                    if (sock == null) {
                        kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.Main) { stressing = false }
                        uiLog("压测失败: VPN 未连接"); return@launch
                    }
                    val payload = ByteArray(500) { 'Z'.code.toByte() }
                    val addr = java.net.InetAddress.getByName(targetIp)
                    val pkt = DatagramPacket(payload, payload.size, addr, port)
                    val t0 = System.nanoTime()
                    var nextT = t0
                    val interval = 1_000_000L // 1ms
                    while (sent < count) {
                        sock.send(pkt)
                        sent++
                        nextT += interval
                        while (System.nanoTime() < nextT) { /* busy-wait 校准 1ms */ }
                        if (sent % 1000L == 0L) {
                            uiLog("压测已发 $sent 包 (${(System.nanoTime() - t0) / 1_000_000_000.0}s)")
                        }
                    }
                    sock.close()
                    val elapsedMs = (System.nanoTime() - t0) / 1_000_000L
                    val pps = if (elapsedMs > 0) sent * 1000L / elapsedMs else 0
                    kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.Main) { stressing = false }
                    uiLog("压测发送完成: $sent 包 500B → $targetIp:$port, 耗时 ${elapsedMs / 1000.0}s ($pps pps)")
                } catch (e: Exception) {
                    kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.Main) { stressing = false }
                    uiLog("压测发送异常: ${e.message}")
                }
            }
        }, modifier = Modifier.height(32.dp), colors = ButtonDefaults.buttonColors(containerColor = if (stressing) Color(0xFFF59E0B) else Color(0xFF7C3AED)),
            contentPadding = PaddingValues(horizontal = 12.dp, vertical = 0.dp)) { Text(if (stressing) "压测中..." else "压测发送", fontSize = 11.sp) }

        Spacer(Modifier.height(16.dp))

        // ── 日志区 ──
        Text("日志 (${logLines.size})", fontSize = 11.sp, color = Color(0xFF64748B))
        Spacer(Modifier.height(4.dp))
        Box(modifier = Modifier.fillMaxWidth().heightIn(max = 400.dp).background(Color(0xFF020617), RoundedCornerShape(6.dp))
            .border(1.dp, Color(0xFF1E293B), RoundedCornerShape(6.dp)).padding(8.dp)) {
            val ds = rememberScrollState()
            Column(modifier = Modifier.verticalScroll(ds)) {
                if (logLines.isEmpty()) Text("等待 UDP 数据...", fontSize = 9.sp, color = Color(0xFF475569))
                logLines.takeLast(100).forEach { line ->
                    val isRx = line.startsWith("RX")
                    Text(line, fontSize = 9.sp, color = if (isRx) Color(0xFF38BDF8) else Color(0xFF94A3B8),
                        lineHeight = 13.sp, modifier = Modifier.padding(vertical = 1.dp))
                }
            }
        }
        TextButton(onClick = { logLines = emptyList() }) { Text("清空日志", fontSize = 9.sp, color = Color(0xFF64748B)) }
    }
}

@Composable
private fun RowScope.Field(value: String, onChange: (String) -> Unit) {
    Box(modifier = Modifier.weight(1f).height(32.dp).background(Color(0xFF0B1121), RoundedCornerShape(6.dp))
        .border(1.dp, Color(0xFF334155), RoundedCornerShape(6.dp)).padding(horizontal = 10.dp),
        contentAlignment = Alignment.CenterStart) {
        BasicTextField(value = value, onValueChange = onChange, singleLine = true,
            textStyle = TextStyle(fontSize = 12.sp, color = Color(0xFFE2E8F0)),
            cursorBrush = androidx.compose.ui.graphics.SolidColor(Color(0xFF38BDF8)))
    }
}

@Composable
private fun TextButton(onClick: () -> Unit, content: @Composable () -> Unit) {
    androidx.compose.material3.TextButton(onClick = onClick, content = { content() },
        modifier = Modifier.height(28.dp), contentPadding = PaddingValues(horizontal = 8.dp, vertical = 0.dp))
}

private fun timeNow(): String =
    java.text.SimpleDateFormat("HH:mm:ss.SSS", java.util.Locale.US).format(java.util.Date())

