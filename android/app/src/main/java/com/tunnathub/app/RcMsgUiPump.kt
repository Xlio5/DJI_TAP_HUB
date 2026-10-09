package com.tunnathub.app

import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicReference

/** rcmsg 接收与 Compose UI 更新之间的节拍隔离器。 */
class RcMsgUiPump<T>(
    private val nowMs: () -> Long = { System.currentTimeMillis() }
) {
    private val packetCount = AtomicInteger()
    private val latest = AtomicReference<T?>(null)
    private var lastRateCount = 0
    private var lastRateAtMs = nowMs()

    fun notePacket(packet: T) {
        latest.set(packet)
        packetCount.incrementAndGet()
    }

    fun takeLatestForUi(): T? = latest.getAndSet(null)

    fun sampleReceiveHz(): Float {
        val now = nowMs()
        val dtMs = (now - lastRateAtMs).coerceAtLeast(1L)
        val count = packetCount.get()
        val hz = ((count - lastRateCount).coerceAtLeast(0) * 1000f) / dtMs
        lastRateCount = count
        lastRateAtMs = now
        return hz
    }

    fun getPacketCountForTest(): Int = packetCount.get()
}
