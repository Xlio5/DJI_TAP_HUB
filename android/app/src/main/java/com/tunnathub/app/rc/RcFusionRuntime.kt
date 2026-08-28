package com.tunnathub.app.rc

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/** 运行期桥接: 输入源变化更新最新状态, 发布协程按固定周期输出完整 RC。 */
class RcFusionRuntime(
    private val geteventReaderFactory: ((RcInputSample) -> Unit) -> RcReader,
    private val port40007ReaderFactory: ((RcInputSample) -> Unit) -> Port40007RcReader,
    private val transport: RcMsgTransport,
    private val nowMs: () -> Long = { System.currentTimeMillis() },
    private val publishIntervalMs: Long = 10L,
    private val onError: (String, Throwable) -> Unit = { _, _ -> }
) : AutoCloseable {
    @Volatile private var latestGetevent: RcInputSample? = null
    @Volatile private var latest40007: RcInputSample? = null
    /** 内部健康标志: publish 连续失败超阈值 → false。外层 startRcFusionRuntime 据此重建整个融合 (含新 socket)。 */
    @Volatile var isHealthy: Boolean = true
        private set
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private var job: Job? = null

    fun start() {
        if (job != null) return
        val parent = scope.launch {
            launch {
                while (isActive) {
                    try {
                        geteventReaderFactory { latestGetevent = it }.run()
                    } catch (t: Throwable) {
                        if (isActive) {
                            onError("getevent", t)
                            delay(1000L)
                        }
                    }
                }
            }
            launch {
                while (isActive) {
                    try {
                        port40007ReaderFactory { latest40007 = it }.runBlocking()
                    } catch (t: Throwable) {
                        if (isActive) {
                            onError("40007", t)
                            delay(1000L)
                        }
                    }
                }
            }
            launch publish@{
                var lastPublishMs = 0L
                var consecutivePublishFailures = 0
                while (isActive) {
                    try {
                        val now = nowMs()
                        if (RcFusionEngine.shouldPublish(lastPublishMs, now, publishIntervalMs)) {
                            val ge = latestGetevent
                            val p4 = latest40007
                            val fused = RcFusionEngine.fuse(ge, p4, now)
                            transport.publish(
                                fused,
                                RcFusionEngine.isFresh(ge, now, RcFusionEngine.GETEVENT_FRESH_MS),
                                RcFusionEngine.isFresh(p4, now, RcFusionEngine.PORT40007_FRESH_MS)
                            )
                            lastPublishMs = now
                            consecutivePublishFailures = 0
                        }
                        delay(5L)
                    } catch (e: CancellationException) {
                        throw e
                    } catch (e: Exception) {
                        // 发布失败自愈: 瞬时抖动 (socket 短暂不可写) 短重试;
                        // 连续失败超阈值 → 判定内部死亡, 外层 startRcFusionRuntime 检测 isHealthy=false 后重建整个融合。
                        consecutivePublishFailures++
                        onError("publish", e)
                        if (consecutivePublishFailures >= PUBLISH_FATAL_FAILURES) {
                            isHealthy = false
                            return@publish
                        }
                        delay(20L)
                    }
                }
            }
        }
        job = parent
    }

    override fun close() {
        job?.cancel()
        job = null
        transport.close()
    }

    companion object {
        /** publish 连续失败多少次判定内部死亡 (失败重试间隔 ~20ms, 20 次 ≈ 400ms) */
        private const val PUBLISH_FATAL_FAILURES = 20
    }
}
