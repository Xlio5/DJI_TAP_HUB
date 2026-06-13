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
        const val USB_VID = 0x2207
        const val USB_PID = 0x0010
        private const val USB_TIMEOUT_MS = 1000
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

        if (!usbManager.hasPermission(device)) {
            throw IllegalStateException("USB 权限未授予")
        }

        usbConnection = usbManager.openDevice(device)
            ?: throw IllegalStateException("无法打开 USB 设备")

        // CDC ACM 设备：遍历所有接口找 Bulk 端点
        findEndpoints(device)

        if (epOut == null || epIn == null) {
            throw IllegalStateException("未找到 Bulk 端点")
        }

        // 发送 CDC ACM 控制命令，激活数据通道
        initCdcAcm()

        Log.i(TAG, "USB 已连接: epOut=0x${epOut!!.address.toString(16)}, epIn=0x${epIn!!.address.toString(16)}")
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

    /* ── CDC ACM 初始化 ────────────────────────────── */
    /**
     * 发送 CDC ACM 控制命令 (SET_LINE_CODING + SET_CONTROL_LINE_STATE)
     * 不发送这些命令，CDC ACM 设备不会传输数据。
     */
    private fun initCdcAcm() {
        val conn = usbConnection ?: return
        val device = findDevice() ?: return

        // CDC 控制接口通常是 interface 0
        val ctrlIface = device.getInterface(0)
        val ifaceNum = ctrlIface.id

        // SET_LINE_CODING: 115200 baud, 8N1
        val lineCoding = byteArrayOf(
            0x00.toByte(), 0xC2.toByte(), 0x01.toByte(), 0x00.toByte(),  // 115200 baud (LE)
            0x00.toByte(),                      // 1 stop bit
            0x00.toByte(),                      // no parity
            0x08.toByte()                       // 8 data bits
        )
        var ret = conn.controlTransfer(
            0x21,  // bmRequestType: Host-to-device, Class, Interface
            0x20,  // bRequest: SET_LINE_CODING
            0,     // wValue
            ifaceNum,  // wIndex: interface number
            lineCoding,
            lineCoding.size,
            1000
        )
        Log.i(TAG, "SET_LINE_CODING: $ret")

        // SET_CONTROL_LINE_STATE: DTR=1, RTS=1
        ret = conn.controlTransfer(
            0x21,  // bmRequestType
            0x22,  // bRequest: SET_CONTROL_LINE_STATE
            0x03,  // wValue: DTR(1) | RTS(2)
            ifaceNum,
            null,
            0,
            1000
        )
        Log.i(TAG, "SET_CONTROL_LINE_STATE: $ret")
    }

    /* ── Coroutine 1: TUN → USB ────────────────────────────── */

    private suspend fun tunToUsbLoop(tunInput: FileInputStream) {
        val buf = acquireBuffer()

        while (coroutineContext.isActive && isConnected) {
            try {
                val n = tunInput.read(buf, FrameCodec.FRAME_HEADER_LEN, FrameCodec.FRAME_MAX_PAYLOAD)
                if (n <= 0) { if (n < 0) break; delay(1); continue }

                val payload = buf.copyOfRange(FrameCodec.FRAME_HEADER_LEN, FrameCodec.FRAME_HEADER_LEN + n)
                val frameLen = FrameCodec.pack(buf, payload)
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
        var lastRxTime = System.currentTimeMillis()

        while (coroutineContext.isActive && isConnected) {
            try {
                val n = usbConnection!!.bulkTransfer(epIn, buf, buf.size, USB_TIMEOUT_MS)

                if (n < 0) {
                    val now = System.currentTimeMillis()
                    if (now - lastRxTime > FrameCodec.HEARTBEAT_TIMEOUT_MS) {
                        Log.w(TAG, "心跳超时")
                        break
                    }
                    continue
                }
                if (n == 0) continue
                lastRxTime = System.currentTimeMillis()

                when (val result = FrameCodec.unpack(buf, n)) {
                    is FrameCodec.UnpackResult.Data -> tunOutput.write(result.payload)
                    is FrameCodec.UnpackResult.Heartbeat -> {
                        val pong = ByteArray(FrameCodec.FRAME_HEADER_LEN)
                        FrameCodec.packHeartbeat(pong)
                        usbConnection!!.bulkTransfer(epOut, pong, 0, pong.size, 100)
                    }
                    is FrameCodec.UnpackResult.Credit -> {} // Phase 3
                    is FrameCodec.UnpackResult.MagicMismatch -> Log.w(TAG, "Magic mismatch")
                    is FrameCodec.UnpackResult.Error -> Log.w(TAG, "Frame error: ${result.message}")
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
