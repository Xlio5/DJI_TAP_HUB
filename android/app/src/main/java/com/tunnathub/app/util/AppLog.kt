/**
 * AppLog.kt — 统一日志收集器
 *
 * 所有模块调用 AppLog.d/i/w/e() 写入日志。
 * 日志同时输出到 android.util.Log (ADB) 和内存中的环形缓冲区 (UI)。
 * Compose 可观察 logs StateFlow 实时渲染调试面板。
 */

package com.tunnathub.app.util

import android.util.Log
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

object AppLog {
    /** 最多保留 200 条日志 */
    private const val MAX_ENTRIES = 200

    /** 日志等级 */
    enum class Level(val emoji: String) {
        DEBUG(""),
        INFO(""),
        WARN("⚠"),
        ERROR("❌"),
    }

    /** 单条日志 */
    data class Entry(
        val timestamp: Long,
        val level: Level,
        val tag: String,
        val message: String,
    ) {
        val timeStr: String get() {
            val s = (timestamp / 1000) % 60
            val m = (timestamp / 60000) % 60
            val h = (timestamp / 3600000) % 24
            return "%02d:%02d:%02d".format(h, m, s)
        }
        val fullLine: String get() {
            val prefix = if (level.emoji.isNotEmpty()) "${level.emoji} " else ""
            return "$timeStr $prefix[$tag] $message"
        }
    }

    private val _logs = MutableStateFlow<List<Entry>>(emptyList())
    val logs: StateFlow<List<Entry>> = _logs.asStateFlow()

    /** 最近的日志 (最近 50 条，从新到旧) */
    val recent: List<Entry> get() = _logs.value.takeLast(50).reversed()

    fun d(tag: String, message: String) = log(Level.DEBUG, tag, message)
    fun i(tag: String, message: String) = log(Level.INFO, tag, message)
    fun w(tag: String, message: String) = log(Level.WARN, tag, message)
    fun e(tag: String, message: String, throwable: Throwable? = null) {
        val msg = if (throwable != null) "$message: ${throwable.message}" else message
        log(Level.ERROR, tag, msg)
    }

    @Synchronized
    private fun log(level: Level, tag: String, message: String) {
        // 同步输出到 Android Log
        val tagWithLevel = "TUN[$tag]"
        when (level) {
            Level.DEBUG -> Log.d(tagWithLevel, message)
            Level.INFO  -> Log.i(tagWithLevel, message)
            Level.WARN  -> Log.w(tagWithLevel, message)
            Level.ERROR -> {
                Log.e(tagWithLevel, message)
                // 同时输出到 stdout 确保被 logcat 捕获
                println("[TUN_ERROR] $tag: $message")
            }
        }

        // 写入环形缓冲
        val entry = Entry(System.currentTimeMillis(), level, tag, message)
        val current = _logs.value.toMutableList()
        current.add(entry)
        if (current.size > MAX_ENTRIES) {
            current.removeAt(0)
        }
        _logs.value = current
    }

    fun clear() {
        _logs.value = emptyList()
    }
}
