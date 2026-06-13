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

import android.content.Context
import android.hardware.usb.*
import android.os.ParcelFileDescriptor
import android.util.Log
import com.tunnathub.app.proto.FrameCodec
import kotlinx.coroutines.*
import kotlin.coroutines.coroutineContext
import java.io.FileInputStream
import java.io.FileOutputStream
import java.util.concurrent.ConcurrentLinkedQueue

class UsbBridge(
    private val context: Context,
    private val tunFd: ParcelFileDescriptor
) {
    companion object {
        private const val TAG = "UsbBridge"
        const val USB_VID = 0x0BDA
        const val USB_PID = 0x8812
        private const val USB_TIMEOUT_MS = 10  // 10ms 超低延迟

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

    private var usbConnection: UsbDeviceConnection? = null
    private var epOut: UsbEndpoint? = null  // Bulk-OUT: Android → RK3588
    private var epIn: UsbEndpoint? = null   // Bulk-IN:  RK3588 → Android

    private val bufferPool = ConcurrentLinkedQueue<ByteArray>()

    init {
        repeat(16) { bufferPool.offer(ByteArray(FrameCodec.FRAME_MAX_LEN)) }
    }

    /**
     * 启动双协程转发
     */
    suspend fun start(scope: CoroutineScope) {
        val device = findDevice() ?: throw IllegalStateException("未找到 TUN_NAT_HUB USB 设备")
        val usbManager = context.getSystemService(Context.USB_SERVICE) as UsbManager

        // 直接打开设备（device_filter.xml 已声明，应自动获得权限）
        usbConnection = usbManager.openDevice(device)
            ?: throw IllegalStateException("无法打开 USB 设备，请重新插拔 USB 线并授权")

        // 遍历所有接口找 Bulk 端点
        findEndpoints(device)

        if (epOut == null || epIn == null) {
            throw IllegalStateException("未找到 Bulk 端点")
        }

        Log.i(TAG, "USB 已连接: epOut=0x${epOut!!.address.toString(16)}, epIn=0x${epIn!!.address.toString(16)}")

        // 发送 DTR/RTS 激活 g_serial TTY 数据通道
        activateTty()

        isConnected = true
        onLinkStateChange?.invoke(LinkState.Connected)

        val tunInput = FileInputStream(tunFd.fileDescriptor)
        val tunOutput = FileOutputStream(tunFd.fileDescriptor)

        val job1 = scope.launch(Dispatchers.IO) { tunToUsbLoop(tunInput) }
        val job2 = scope.launch(Dispatchers.IO) { usbToTunLoop(tunOutput) }

        try {
            job1.join()
            job2.join()
        } catch (_: CancellationException) {}
    }

    /**
     * CDC ACM 设备有两个接口：
     *   Interface 0: Communication (control)
     *   Interface 1: Data (bulk endpoints)
     * 遍历所有接口和端点找到 Bulk IN/OUT
     */
    private fun findEndpoints(device: UsbDevice) {
        for (i in 0 until device.interfaceCount) {
            val iface = device.getInterface(i)
            // 声明接口
            if (!usbConnection!!.claimInterface(iface, true)) {
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

        while (coroutineContext.isActive && isConnected) {
            try {
                // 直接读入 buf[4..]，省去一次拷贝
                val n = tunInput.read(buf, FrameCodec.FRAME_HEADER_LEN, FrameCodec.FRAME_MAX_PAYLOAD)
                if (n <= 0) { if (n < 0) break; delay(1); continue }

                // 原地写帧头（零拷贝）
                val frameLen = FrameCodec.writeHeader(buf, n)
                val written = usbConnection!!.bulkTransfer(epOut, buf, 0, frameLen, USB_TIMEOUT_MS)

                if (written < 0) { Log.e(TAG, "USB write 失败"); break }
            } catch (e: Exception) {
                if (coroutineContext.isActive) Log.e(TAG, "TUN→USB 异常", e)
                break
            }
        }
        releaseBuffer(buf)
        Log.i(TAG, "TUN→USB 退出")
    }

    /* ── Coroutine 2: USB → TUN ────────────────────────────── */

    private suspend fun usbToTunLoop(tunOutput: FileOutputStream) {
        val buf = acquireBuffer()

        while (coroutineContext.isActive && isConnected) {
            try {
                val n = usbConnection!!.bulkTransfer(epIn, buf, buf.size, USB_TIMEOUT_MS)

                if (n < 0) {
                    // USB timeout/busy — no data available, keep waiting
                    if (!isConnected) break
                    continue
                }
                if (n == 0) continue

                when (val result = FrameCodec.unpack(buf, n)) {
                    is FrameCodec.UnpackResult.Data -> tunOutput.write(result.payload)
                    is FrameCodec.UnpackResult.Heartbeat -> {
                        usbConnection!!.bulkTransfer(epOut, PONG_FRAME, 0, PONG_FRAME.size, 100)
                    }
                    is FrameCodec.UnpackResult.Credit -> {} // Phase 3
                    is FrameCodec.UnpackResult.MagicMismatch -> {
                        // Skip corrupt byte and resync
                    }
                    is FrameCodec.UnpackResult.Error -> {} // Ignore
                }
            } catch (e: Exception) {
                if (coroutineContext.isActive) Log.e(TAG, "USB→TUN 异常", e)
                break
            }
        }
        releaseBuffer(buf)
        isConnected = false
        onLinkStateChange?.invoke(LinkState.Disconnected)
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
        isConnected = false
        onLinkStateChange?.invoke(LinkState.Disconnected)
        try { usbConnection?.close() } catch (_: Exception) {}
        usbConnection = null
    }
}

enum class LinkState { Disconnected, Connected, Reconnecting }
