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
    var logLines by remember { mutableStateOf(listOf<String>()) }
    val scope = rememberCoroutineScope()

    // 监听 socket (持引用, 页面离开时关闭)
    var recvSock by remember { mutableStateOf<DatagramSocket?>(null) }
    // 监听循环控制: 用 AtomicBoolean 而非 Compose state (避免 IO 协程读快照问题)
    val runFlag = remember { java.util.concurrent.atomic.AtomicBoolean(false) }

    fun addLog(line: String) {
        logLines = (logLines + "[${timeNow()}] $line").takeLast(200)
    }

    Column(modifier = Modifier.fillMaxSize().background(Color(0xFF0F172A)).verticalScroll(rememberScrollState()).padding(16.dp)) {
        Text("UDP 工具 (特殊调试版)", fontSize = 15.sp, color = Color(0xFF38BDF8), fontWeight = androidx.compose.ui.text.font.FontWeight.Bold)
        Text("局域网 UDP 收发 · 手机 IP = ${TunNatVpnService.currentLanAddr}", fontSize = 9.sp, color = Color(0xFF64748B))

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
                    // 启动监听: openProtectedPort 绑定 144.11:port (能收隧道包)
                    val sock = TunNatVpnService.openProtectedPort(port)
                    if (sock == null) { addLog("监听失败: 无法打开端口 $port"); return@Button }
                    sock.soTimeout = 500
                    recvSock = sock
                    runFlag.set(true)
                    listening = true
                    addLog("开始监听 ${TunNatVpnService.currentLanAddr}:$port (电脑发此地址:端口)")
                    scope.launch(Dispatchers.IO) {
                        val buf = ByteArray(2048)
                        while (runFlag.get()) {
                            try {
                                val pkt = DatagramPacket(buf, buf.size)
                                sock.receive(pkt)
                                val data = pkt.data.copyOf(pkt.length)
                                val hex = data.take(32).joinToString(" ") { "%02x".format(it) }
                                val ascii = String(data, Charsets.UTF_8).replace(Regex("[^\\x20-\\x7E]"), ".")
                                val line1 = "RX ${pkt.length}B from ${pkt.address?.hostAddress}:${pkt.port} [$hex]"
                                val line2 = if (ascii.isNotBlank()) "   ASCII: $ascii" else null
                                kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.Main) {
                                    logLines = (logLines + "[${timeNow()}] $line1").takeLast(200)
                                    if (line2 != null) logLines = (logLines + "[${timeNow()}] $line2").takeLast(200)
                                }
                            } catch (_: java.net.SocketTimeoutException) {
                            } catch (e: Exception) {
                                if (runFlag.get()) {
                                    kotlinx.coroutines.withContext(kotlinx.coroutines.Dispatchers.Main) {
                                        logLines = (logLines + "[${timeNow()}] RX err: ${e.message}").takeLast(200)
                                    }
                                }
                                break
                            }
                        }
                    }
                } else {
                    runFlag.set(false)
                    listening = false
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
                    val sock = DatagramSocket(null)
                    sock.bind(InetSocketAddress(TunNatVpnService.currentLanAddr, 0))
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
