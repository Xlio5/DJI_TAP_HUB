package com.tunnathub.app.rc

import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch

/** 双输入源实时到达速率 (Hz)，供遥控页诊断分别显示 getevent / 40007。 */
data class RcSourceStats(
    val geteventHz: Float = 0f,
    val p40007Hz: Float = 0f
)

/** 运行期桥接: 输入源变化更新最新状态, 发布协程按固定周期输出完整 RC。 */
class RcFusionRuntime(
    private val geteventReaderFactory: ((RcInputSample) -> Unit) -> RcReader,
    private val port40007ReaderFactory: ((RcInputSample) -> Unit) -> Port40007RcReader,
    private val transport: RcMsgTransport,
    private val nowMs: () -> Long = { System.currentTimeMillis() },
    private val publishIntervalMs: Long = 10L,
    private val onError: (String, Throwable) -> Unit = { _, _ -> },
    private val onSourceStats: (RcSourceStats) -> Unit = {}
) : AutoCloseable {
    @Volatile private var latestGetevent: RcInputSample? = null
    @Volatile private var latest40007: RcInputSample? = null
    // 双源到达速率统计: 每次 reader 回调按到达间隔取倒数, 指数平滑 (0.7 旧 + 0.3 新) 抗抖动
    @Volatile private var geteventHz = 0f
    @Volatile private var p40007Hz = 0f
    @Volatile private var geteventLastAtMs = 0L
    @Volatile private var p40007LastAtMs = 0L
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
                        geteventReaderFactory { noteGetevent(it) }.run()
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
                        port40007ReaderFactory { note40007(it) }.runBlocking()
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

    private fun noteGetevent(sample: RcInputSample) {
        latestGetevent = sample
        val now = nowMs()
        geteventHz = updateRate(geteventHz, geteventLastAtMs, now)
        geteventLastAtMs = now
        emitSourceStats()
    }

    private fun note40007(sample: RcInputSample) {
        latest40007 = sample
        val now = nowMs()
        p40007Hz = updateRate(p40007Hz, p40007LastAtMs, now)
        p40007LastAtMs = now
        emitSourceStats()
    }

    /** 按到达间隔取倒数得到瞬时 Hz 并指数平滑; 首次到达或断流(>10s)从 0 重新起算。 */
    private fun updateRate(currentHz: Float, lastAtMs: Long, nowMs: Long): Float {
        if (lastAtMs <= 0L) return 0f
        val dt = nowMs - lastAtMs
        if (dt < 1) return currentHz
        if (dt > SOURCE_RESET_MS) return 0f
        val inst = 1000f / dt
        return if (currentHz <= 0f) inst else currentHz * 0.7f + inst * 0.3f
    }

    /** 上报时对停止更新的源做老化归零 (各自阈值覆盖正常帧间隔, 避免低频 40007 闪烁)。 */
    private fun emitSourceStats() {
        val now = nowMs()
        val ge = if (geteventLastAtMs > 0L && now - geteventLastAtMs > GETEVENT_STALE_MS) 0f else geteventHz
        val p4 = if (p40007LastAtMs > 0L && now - p40007LastAtMs > PORT40007_STALE_MS) 0f else p40007Hz
        onSourceStats(RcSourceStats(ge, p4))
    }

    override fun close() {
        job?.cancel()
        job = null
        transport.close()
    }

    companion object {
        /** publish 连续失败多少次判定内部死亡 (失败重试间隔 ~20ms, 20 次 ≈ 400ms) */
        private const val PUBLISH_FATAL_FAILURES = 20
        /** 源断流多久后速率归零重新起算 (覆盖 40007 的 ~2.5s 低频帧间隔) */
        private const val SOURCE_RESET_MS = 10_000L
        /** getevent 高频源停止多久老化归零 */
        private const val GETEVENT_STALE_MS = 2_000L
        /** 40007 低频源停止多久老化归零 (> 实测 ~2.5s 帧间隔, 避免帧间显示跳动) */
        private const val PORT40007_STALE_MS = 4_000L
    }
}
