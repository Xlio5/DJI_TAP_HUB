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
        private const val USB_TIMEOUT_MS = 10  // 10ms 超低延迟

        /** USB 写连续失败多少次才判定链路断开 (滤掉瞬时抖动) */
        private const val MAX_USB_WRITE_FAILS = 5

        /** 预分配的 PONG 缓冲区（避免重复分配） */
        private val PONG_FRAME: ByteArray = run {
            val b = ByteArray(FrameCodec.FRAME_HEADER_LEN)
            FrameCodec.packHeartbeat(b)
            b
        }
    }

    /** 已成功 openDevice 过的设备标识 (VID:PID)。
     *  DJI RC 会对 0BDA:8812 反复重枚举 → hasPermission 变 false → 每次 requestPermission 弹窗。
     *  一旦授权过就记住, 重连时跳过重复授权, 直接 openDevice。 */
    private val grantedDevices = java.util.concurrent.ConcurrentHashMap<String, Boolean>()

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
        // 修复: DJI RC 会反复重枚举 0BDA:8812 → hasPermission 变 false → 每次都 requestPermission 弹权限框。
        // 已成功 openDevice 过的设备 (VID:PID) 跳过 requestPermission, 直接尝试 openDevice。
        val deviceKey = "${device.vendorId}:${device.productId}"
        val alreadyGranted = grantedDevices.containsKey(deviceKey)
        if (!alreadyGranted && !usbManager.hasPermission(device)) {
            requestPermissionBlocking(device)
        }

        // 打开设备; 若已授权过但系统重枚举后仍误判未授权, openDevice 抛 SecurityException → 回退请求一次
        val conn = try {
            usbManager.openDevice(device)
        } catch (e: SecurityException) {
            AppLog.w(TAG, "openDevice 权限异常, 回退请求权限: ${e.message}")
            requestPermissionBlocking(device)
            usbManager.openDevice(device)
        }
        usbConnection = conn
            ?: throw IllegalStateException("无法打开 USB 设备，请重新插拔 USB 线并授权")
        // 记录已授权, 后续重连 (DJI 重枚举) 不再弹窗
        grantedDevices[deviceKey] = true
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
     * 阻塞请求 USB 权限 (最多等 2s)。
     * 仅在设备首次连接或已授权集合外才调用, 避免 DJI 重枚举导致反复弹窗。
     */
    private fun requestPermissionBlocking(device: UsbDevice) {
        val usbManager = context.getSystemService(Context.USB_SERVICE) as UsbManager
        Log.w(TAG, "USB 权限未授予，正在请求...")
        AppLog.w(TAG, "USB 权限未授予，正在请求...")
        val latch = CountDownLatch(1)
        val permAction = "com.tunnathub.app.USB_PERM"
        val receiver = object : BroadcastReceiver() {
            override fun onReceive(ctx: Context, intent: Intent) {
                if (permAction == intent.action) {
                    val granted = intent.getBooleanExtra(UsbManager.EXTRA_PERMISSION_GRANTED, false)
                    Log.i(TAG, "USB 权限结果: $granted")
                    AppLog.i(TAG, "USB 权限${if (granted) "已" else "未"}授予")
                    latch.countDown()
                }
            }
        }
        context.registerReceiver(receiver, IntentFilter(permAction), Context.RECEIVER_NOT_EXPORTED)
        val pi = PendingIntent.getBroadcast(context, 0,
            Intent(permAction).setPackage(context.packageName),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        usbManager.requestPermission(device, pi)
        // 等待权限授予（device_filter.xml 匹配时自动授予，无弹窗）
        latch.await(2, TimeUnit.SECONDS)
        try { context.unregisterReceiver(receiver) } catch (_: Exception) {}
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
        val buf = acquireBuffer()
        var firstPacket = true

        while (coroutineContext.isActive && isConnected) {
            try {
                val conn = usbConnection ?: break   // M1: 捕获局部引用, 避免与 disconnect 竞态 NPE
                val epInL = epIn ?: break           // M1: 与 tunToUsbLoop 保持一致, 补 epIn 局部引用
                val epOutL = epOut ?: break
                val n = conn.bulkTransfer(epInL, buf, buf.size, USB_TIMEOUT_MS)

                if (n < 0) {
                    // USB timeout/busy — no data available, keep waiting
                    if (!isConnected) break
                    continue
                }
                if (n == 0) continue
                notifyActive()

                when (val result = FrameCodec.unpack(buf, n)) {
                    is FrameCodec.UnpackResult.Data -> tunOutput.write(result.payload)
                    is FrameCodec.UnpackResult.Heartbeat -> {
                        if (firstPacket) { AppLog.d(TAG, "USB→TUN 首帧: 心跳 PONG"); firstPacket = false }
                        conn.bulkTransfer(epOutL, PONG_FRAME, 0, PONG_FRAME.size, 100)
                    }
                    is FrameCodec.UnpackResult.Credit -> {} // Phase 3
                    is FrameCodec.UnpackResult.MagicMismatch -> {
                        // Skip corrupt byte and resync
                    }
                    is FrameCodec.UnpackResult.Error -> {} // Ignore
                }
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
