package com.tunnathub.app

import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicReference

/** rcmsg 接收与 Compose UI 更新之间的节拍隔离器。 */
class RcMsgUiPump<T>(
    private val nowMs: () -> Long = { System.currentTimeMillis() }
) {
    private val packetCount = AtomicInteger()
    private val latest = AtomicReference<T?>(null)
    private val edgeQueue = ArrayDeque<T>()
    private val edgeLock = Any()
    private var hasEdgeKey = false
    private var lastEdgeKey = 0L
    private var lastRateCount = 0
    private var lastRateAtMs = nowMs()

    fun notePacket(packet: T) {
        latest.set(packet)
        packetCount.incrementAndGet()
    }

    fun notePacket(packet: T, edgeKey: Long) {
        synchronized(edgeLock) {
            latest.set(packet)
            if (!hasEdgeKey) {
                hasEdgeKey = true
                lastEdgeKey = edgeKey
            } else if (edgeKey != lastEdgeKey) {
                if (edgeQueue.size >= EDGE_QUEUE_CAPACITY) edgeQueue.removeFirst()
                edgeQueue.addLast(packet)
                lastEdgeKey = edgeKey
            }
        }
        packetCount.incrementAndGet()
    }

    fun takeLatestForUi(): T? = synchronized(edgeLock) {
        if (edgeQueue.isNotEmpty()) {
            edgeQueue.removeFirst().also { latest.compareAndSet(it, null) }
        } else {
            latest.getAndSet(null)
        }
    }

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

    companion object {
        private const val EDGE_QUEUE_CAPACITY = 32
    }
}
