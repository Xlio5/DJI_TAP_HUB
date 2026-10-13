/**
 * UsbBridge.kt — USB Host 通信 + TUN ↔ USB 转发 (CDC ACM 版本)
 *
 * CDC ACM 提供 2 个 Bulk 端点 (IN + OUT)，Android 通过 USB Host API 直接读写。
 *
 * 双协程:
 *   Coroutine 1 (tunToUsb): TUN.read() → framePack → USB.bulkTransfer(OUT)
 *   Coroutine 2 (usbToTun): USB.bulkTransfer(IN) → frameUnpack → TUN.write()
 */

package com.tunnathub.app.usb

import android.app.PendingIntent
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.hardware.usb.*
import android.os.ParcelFileDescriptor
import android.util.Log
import com.tunnathub.app.proto.FrameCodec
import com.tunnathub.app.util.AppLog
import kotlinx.coroutines.*
import kotlin.coroutines.coroutineContext
import java.io.FileInputStream
import java.io.FileOutputStream
import java.util.concurrent.ConcurrentLinkedQueue
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

class UsbBridge(
    private val context: Context,
    private val tunFd: ParcelFileDescriptor
) {
    companion object {
        private const val TAG = "UsbBridge"
        const val USB_VID = 0x0BDA
        const val USB_PID = 0x8812
        private const val USB_TIMEOUT_MS = 50  // 50ms：突发(关键帧~160KB)时让 bulk 一次收满, 降低丢包

        /** USB 写连续失败多少次才判定链路断开 (滤掉瞬时抖动) */
        private const val MAX_USB_WRITE_FAILS = 5

        /** 预分配的 PONG 缓冲区（避免重复分配） */
        private val PONG_FRAME: ByteArray = run {
            val b = ByteArray(FrameCodec.FRAME_HEADER_LEN)
            FrameCodec.packHeartbeat(b)
            b
        }
    }

    @Volatile var isConnected = false
        private set

    var onLinkStateChange: ((LinkState) -> Unit)? = null

    @Volatile private var usbConnection: UsbDeviceConnection? = null
    @Volatile private var epOut: UsbEndpoint? = null  // Bulk-OUT: Android → RK3588
    @Volatile private var epIn: UsbEndpoint? = null   // Bulk-IN:  RK3588 → Android

    /** 断开通知去重标志: 双协程任一退出即置 isConnected=false + 触发 Disconnected, 只通知一次 */
    private val disconnectedNotified = java.util.concurrent.atomic.AtomicBoolean(false)
    private val activeNotified = java.util.concurrent.atomic.AtomicBoolean(false)

    private val bufferPool = ConcurrentLinkedQueue<ByteArray>()

    init {
        repeat(16) { bufferPool.offer(ByteArray(FrameCodec.FRAME_MAX_LEN)) }
    }

    /**
     * 启动双协程转发
     * 冷启/重启后 USB 权限可能丢失，先检查并请求权限再打开设备
     */
    suspend fun start(scope: CoroutineScope) {
        // 幂等: 已连接则先断开, 避免重复 openDevice/协程 (解决多次连接卡死)
        if (isConnected) disconnect()
        val device = findDevice() ?: throw IllegalStateException("未找到 TUN_NAT_HUB USB 设备")
        val usbManager = context.getSystemService(Context.USB_SERVICE) as UsbManager
        AppLog.i(TAG, "找到 USB 设备: VID=0x${USB_VID.toString(16)} PID=0x${USB_PID.toString(16)}")

        // 检查 USB 权限。
        // 修复: V3s/DJI RC 会反复重枚举 0BDA:8812 → 设备路径 (deviceName) 变化 → hasPermission 变 false。
        // Android 的 hasPermission 按设备路径校验, 不能按 VID:PID 缓存跳权 (路径变了缓存失效),
        // 否则跳过授权 → openDevice 抛 SecurityException → USB 隧道建不起来 → VPN 无路由 → 播放失败。
        // 每次按 hasPermission 判定: false 则请求授权 (会弹窗或 device_filter 自动授予), 被拒则抛错让上层重试。
        var granted = usbManager.hasPermission(device)
        if (!granted) {
            granted = requestPermissionBlocking(device)
        }
        if (!granted) {
            throw IllegalStateException("USB 权限被拒绝, 无法打开设备 (可能需在系统设置重新授权)")
        }

        // 打开设备 (权限已确认, 正常不会 SecurityException; 万一仍抛则透传错误信息)
        val conn = try {
            usbManager.openDevice(device)
        } catch (e: SecurityException) {
            AppLog.w(TAG, "openDevice 权限异常: ${e.message}")
            throw IllegalStateException("USB 设备打开被拒 (权限异常): ${e.message}", e)
        }
        usbConnection = conn
            ?: throw IllegalStateException("无法打开 USB 设备，请重新插拔 USB 线并授权")
        // 新连接周期: 重置断开通知标志 (同实例重连时)
        disconnectedNotified.set(false)
        activeNotified.set(false)
        AppLog.i(TAG, "USB openDevice 成功")

        // 遍历所有接口找 Bulk 端点
        findEndpoints(device)

        if (epOut == null || epIn == null) {
            throw IllegalStateException("未找到 Bulk 端点")
        }

        // H-01: 捕获局部引用, 避免在日志输出窗口与 disconnect() 置 null 的竞态 NPE
        val outEp = epOut ?: throw IllegalStateException("epOut 为空")
        val inEp = epIn ?: throw IllegalStateException("epIn 为空")
        Log.i(TAG, "USB 已连接: epOut=0x${outEp.address.toString(16)}, epIn=0x${inEp.address.toString(16)}")
        AppLog.i(TAG, "USB 已连接 epOut=0x${outEp.address.toString(16)} epIn=0x${inEp.address.toString(16)}")

        // 发送 DTR/RTS 激活 g_serial TTY 数据通道
        activateTty()

        isConnected = true
        AppLog.i(TAG, "双协程启动，开始 TUN↔USB 转发")

        val tunInput = FileInputStream(tunFd.fileDescriptor)
        val tunOutput = FileOutputStream(tunFd.fileDescriptor)

        val job1 = scope.launch(Dispatchers.IO) { tunToUsbLoop(tunInput) }
        val job2 = scope.launch(Dispatchers.IO) { usbToTunLoop(tunOutput) }

        try {
            job1.join()
            job2.join()
        } catch (e: CancellationException) {
            // H-01: 协程被取消时不吞异常, 重抛让调用方 (doReconnect) 感知取消,
            // 避免 stopVpn() 后 isRunning 被错误覆写为 true
            if (!coroutineContext.isActive) throw e
            // 否则: 协程自己完成了, 忽略
        }
    }

    /**
     * 阻塞请求 USB 权限 (最多等 3s), 返回是否被授予。
     * 冷启/重枚举后设备路径变化, hasPermission 变 false, 需要重新请求授权。
     * 返回 false 表示被拒或超时, 调用方抛错让上层重连循环重试。
     */
    private fun requestPermissionBlocking(device: UsbDevice): Boolean {
        val usbManager = context.getSystemService(Context.USB_SERVICE) as UsbManager
        Log.w(TAG, "USB 权限未授予，正在请求...")
        AppLog.w(TAG, "USB 权限未授予，正在请求...")
        val latch = CountDownLatch(1)
        val grantedResult = java.util.concurrent.atomic.AtomicBoolean(false)
        val permAction = "com.tunnathub.app.USB_PERM"
        val receiver = object : BroadcastReceiver() {
            override fun onReceive(ctx: Context, intent: Intent) {
                if (permAction == intent.action) {
                    val g = intent.getBooleanExtra(UsbManager.EXTRA_PERMISSION_GRANTED, false)
                    grantedResult.set(g)
                    Log.i(TAG, "USB 权限结果: $g")
                    AppLog.i(TAG, "USB 权限${if (g) "已" else "未"}授予")
                    latch.countDown()
                }
            }
        }
        context.registerReceiver(receiver, IntentFilter(permAction), Context.RECEIVER_NOT_EXPORTED)
        val pi = PendingIntent.getBroadcast(context, 0,
            Intent(permAction).setPackage(context.packageName),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        try {
            usbManager.requestPermission(device, pi)
            // DJI RC 上会弹系统窗且无"记住"选项 → 用 Shizuku 自动点"确定" (无人值守)
            UsbPermAutoApprover.scheduleApprove()
            // 等待权限授予（device_filter.xml 匹配时自动授予，无弹窗）
            latch.await(3, TimeUnit.SECONDS)
        } catch (e: Exception) {
            AppLog.w(TAG, "requestPermission 异常: ${e.message}")
        } finally {
            try { context.unregisterReceiver(receiver) } catch (_: Exception) {}
        }
        return grantedResult.get()
    }

    /**
     * CDC ACM 设备有两个接口：
     *   Interface 0: Communication (control)
     *   Interface 1: Data (bulk endpoints)
     * 遍历所有接口和端点找到 Bulk IN/OUT
     */
    private fun findEndpoints(device: UsbDevice) {
        // H-01: 捕获局部引用, 避免与 disconnect() 竞态
        val conn = usbConnection ?: throw IllegalStateException("usbConnection 为空")
        for (i in 0 until device.interfaceCount) {
            val iface = device.getInterface(i)
            // 声明接口
            if (!conn.claimInterface(iface, true)) {
                Log.w(TAG, "无法声明接口 $i")
                continue
            }
            // 找端点
            for (j in 0 until iface.endpointCount) {
                val ep = iface.getEndpoint(j)
                if (ep.type == UsbConstants.USB_ENDPOINT_XFER_BULK) {
                    when (ep.direction) {
                        UsbConstants.USB_DIR_OUT -> epOut = ep
                        UsbConstants.USB_DIR_IN  -> epIn = ep
                    }
                    Log.i(TAG, "Bulk端点: addr=0x${ep.address.toString(16)} dir=${if (ep.direction == UsbConstants.USB_DIR_OUT) "OUT" else "IN"}")
                }
            }
        }
    }

    /**
     * 任一转发协程退出时统一通知断开 (去重)。
     * 修复: 之前只有 usbToTunLoop 触发 Disconnected; tunToUsbLoop 写失败退出时
     * 不通知 → isRunning 不变 → UI 卡在"断开"无法重连。
     */
    private fun notifyDisconnected(reason: String) {
        if (disconnectedNotified.compareAndSet(false, true)) {
            isConnected = false
            activeNotified.set(false)
            onLinkStateChange?.invoke(LinkState.Disconnected)
            AppLog.w(TAG, "USB Bridge 已断开 ($reason)")
        }
    }

    private fun notifyActive() {
        if (activeNotified.compareAndSet(false, true)) {
            onLinkStateChange?.invoke(LinkState.Connected)
        }
    }

    /**
     * 通过 USB Control Transfer 发送 DTR/RTS 信号。
     * g_serial 的 TTY 层需要 DTR 才能开始传输数据。
     * 即使在 use_acm=0 模式下，gs_tty 驱动也会检查 DTR 信号。
     */
    private fun activateTty() {
        val conn = usbConnection ?: return
        // SET_CONTROL_LINE_STATE: bmReqType=0x21(Host→IFace,Class), bReq=0x22, wVal=DTR|RTS
        val ret = conn.controlTransfer(
            0x21, 0x22, 0x03, 0, null, 0, 100
        )
        Log.i(TAG, "SET_CONTROL_LINE_STATE(DTR+RTS): ret=$ret (${if (ret >= 0) "OK" else "ignored"})")
    }

    /* ── Coroutine 1: TUN → USB ────────────────────────────── */

    private suspend fun tunToUsbLoop(tunInput: FileInputStream) {
        val buf = acquireBuffer()
        var firstPacket = true
        var consecutiveFails = 0   // 连续 USB 写失败计数 (滤掉瞬时抖动, 避免误触发重连)

        while (coroutineContext.isActive && isConnected) {
            try {
                val conn = usbConnection ?: break   // M1: 捕获局部引用, 避免与 disconnect 竞态 NPE
                val epOutL = epOut ?: break
                // 直接读入 buf[4..]，省去一次拷贝
                val n = tunInput.read(buf, FrameCodec.FRAME_HEADER_LEN, FrameCodec.FRAME_MAX_PAYLOAD)
                if (n <= 0) { if (n < 0) break; delay(1); continue }

                // 原地写帧头（零拷贝）
                val frameLen = FrameCodec.writeHeader(buf, n)
                val written = conn.bulkTransfer(epOutL, buf, 0, frameLen, USB_TIMEOUT_MS)

                if (firstPacket) { AppLog.d(TAG, "TUN→USB 首包: ${n}B → bulkTransfer wrote=$written"); firstPacket = false }
                if (written < 0) {
                    // 修复: 单次负值可能是瞬时抖动, 连续 MAX_USB_WRITE_FAILS 次才判定链路断开
                    consecutiveFails++
                    if (consecutiveFails >= MAX_USB_WRITE_FAILS) {
                        Log.e(TAG, "USB write 连续失败 $consecutiveFails 次, 判定断开")
                        AppLog.e(TAG, "USB bulkTransfer(OUT) 连续失败 $consecutiveFails 次")
                        break
                    }
                    delay(5)
                    continue
                }
                consecutiveFails = 0
                notifyActive()
            } catch (e: Exception) {
                if (coroutineContext.isActive) Log.e(TAG, "TUN→USB 异常", e)
                break
            }
        }
        releaseBuffer(buf)
        notifyDisconnected("TUN→USB 退出")
        Log.i(TAG, "TUN→USB 退出")
    }

    /* ── Coroutine 2: USB → TUN ────────────────────────────── */

    private suspend fun usbToTunLoop(tunOutput: FileOutputStream) {
        // 读缓冲加大到 16KB：突发时一次 bulkTransfer 能收多个帧，减少读次数，降低内核缓冲溢出丢包
        val buf = ByteArray(16 * 1024)
        var firstPacket = true

        // 流式累积缓冲：bulkTransfer 一次读不保证对齐帧边界。
        // 可能一次读到多个帧（粘包）或半个帧（跨 bulk 边界）。
        // 这里累积数据，按帧头 Magic+Length 逐帧提取，剩余字节留待下次。
        // 累积缓冲 ≥ 读缓冲，避免 arraycopy 越界
        val accum = ByteArray(64 * 1024)
        var accumLen = 0

        while (coroutineContext.isActive && isConnected) {
            try {
                val conn = usbConnection ?: break   // M1: 捕获局部引用, 避免与 disconnect 竞态 NPE
                val epInL = epIn ?: break           // M1: 与 tunToUsbLoop 保持一致, 补 epIn 局部引用
                val epOutL = epOut ?: break

                // 先处理累积缓冲里已能凑齐的完整帧
                var consumed = 0
                while (consumed + FrameCodec.FRAME_HEADER_LEN <= accumLen) {
                    // 帧头前 2 字节必须是 Magic，否则失步（丢弃 1 字节重新对齐）
                    val magic = ((accum[consumed].toInt() and 0xFF) shl 8) or (accum[consumed + 1].toInt() and 0xFF)
                    if (magic != FrameCodec.FRAME_MAGIC.toInt() and 0xFFFF) {
                        consumed++
                        continue
                    }
                    val payloadLen = ((accum[consumed + 2].toInt() and 0xFF) shl 8) or (accum[consumed + 3].toInt() and 0xFF)
                    if (payloadLen > FrameCodec.FRAME_MAX_PAYLOAD) {
                        consumed++  // 长度非法，丢弃该字节重新对齐
                        continue
                    }
                    val frameLen = FrameCodec.FRAME_HEADER_LEN + payloadLen
                    if (consumed + frameLen > accumLen) break  // 帧不完整，等更多数据
                    when {
                        payloadLen == 0 -> {  // 心跳
                            if (firstPacket) { AppLog.d(TAG, "USB→TUN 首帧: 心跳 PONG"); firstPacket = false }
                            conn.bulkTransfer(epOutL, PONG_FRAME, 0, PONG_FRAME.size, 100)
                        }
                        payloadLen == 2 -> {}  // Credit（Phase 3 忽略）
                        else -> {  // 数据帧 → TUN
                            val payload = ByteArray(payloadLen)
                            System.arraycopy(accum, consumed + FrameCodec.FRAME_HEADER_LEN, payload, 0, payloadLen)
                            tunOutput.write(payload)
                        }
                    }
                    consumed += frameLen
                }

                // 处理完的字节移出累积缓冲（保留未消费的尾部）
                if (consumed > 0) {
                    val remaining = accumLen - consumed
                    if (remaining > 0) System.arraycopy(accum, consumed, accum, 0, remaining)
                    accumLen = remaining
                }
                notifyActive()

                // 再读新的数据进累积缓冲
                val n = conn.bulkTransfer(epInL, buf, buf.size, USB_TIMEOUT_MS)
                if (n < 0) {
                    // USB timeout/busy — no data available, keep waiting
                    if (!isConnected) break
                    continue
                }
                if (n == 0) continue
                if (accumLen + n > accum.size) {
                    // 累积缓冲满但没凑齐完整帧：说明帧损坏，清空重新同步
                    accumLen = 0
                    Log.w(TAG, "USB→TUN 累积缓冲溢出, 重新同步")
                }
                System.arraycopy(buf, 0, accum, accumLen, n)
                accumLen += n
            } catch (e: Exception) {
                if (coroutineContext.isActive) { Log.e(TAG, "USB→TUN 异常", e); AppLog.e(TAG, "USB→TUN 异常: ${e.message}", e) }
                break
            }
        }
        releaseBuffer(buf)
        notifyDisconnected("USB→TUN 退出")
        Log.i(TAG, "USB→TUN 退出")
    }

    private fun findDevice(): UsbDevice? {
        val usbManager = context.getSystemService(Context.USB_SERVICE) as UsbManager
        for ((_, device) in usbManager.deviceList) {
            if (device.vendorId == USB_VID && device.productId == USB_PID) {
                Log.i(TAG, "找到设备: ${device.deviceName}")
                return device
            }
        }
        return null
    }

    private fun acquireBuffer() = bufferPool.poll() ?: ByteArray(FrameCodec.FRAME_MAX_LEN)
    private fun releaseBuffer(buf: ByteArray) { bufferPool.offer(buf) }

    fun disconnect() {
        notifyDisconnected("disconnect()")
        try { usbConnection?.close() } catch (_: Exception) {}
        usbConnection = null
    }
}

enum class LinkState { Disconnected, Connected, Reconnecting }
