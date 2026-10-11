package com.tunnathub.app

import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicReference

/** rcmsg 接收与 Compose UI 更新之间的节拍隔离器。 */
class RcMsgUiPump<T>(
    private val nowMs: () -> Long = { System.currentTimeMillis() }
) {
    private val packetCount = AtomicInteger()
    private val latest = AtomicReference<T?>(null)
    private val edgeLock = Any()
    private var hasEdgeKey = false
    private var lastEdgeKey = 0L
    private var lastRateCount = 0
    private var lastRateAtMs = nowMs()

    fun notePacket(packet: T) {
        latest.set(packet)
        packetCount.incrementAndGet()
    }

    fun notePacket(packet: T, edgeKey: Long): T? {
        val edge = synchronized(edgeLock) {
            if (!hasEdgeKey) {
                hasEdgeKey = true
                lastEdgeKey = edgeKey
                latest.set(packet)
                null
            } else if (edgeKey != lastEdgeKey) {
                lastEdgeKey = edgeKey
                // 边沿由即时 Channel 独占，避免周期路径稍后回放旧按键态。
                latest.set(null)
                packet
            } else {
                latest.set(packet)
                null
            }
        }
        packetCount.incrementAndGet()
        return edge
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
