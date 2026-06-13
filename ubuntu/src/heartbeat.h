/**
 * heartbeat.h — 心跳保活 + 统计
 *
 * Ubuntu 端每 1000ms 发送 PING 帧，
 * 3000ms 无 PONG 判定链路断开。
 */

#ifndef USB_TUND_HEARTBEAT_H
#define USB_TUND_HEARTBEAT_H

#include <cstdint>
#include <atomic>
#include <chrono>
#include <functional>
#include <string>

namespace tun_nat {

/// 链路状态
enum class LinkState {
    Disconnected,
    Connected,
    Reconnecting
};

/// 统计信息
struct Stats {
    std::atomic<uint64_t> framesRx{0};    // 接收帧数
    std::atomic<uint64_t> framesTx{0};    // 发送帧数
    std::atomic<uint64_t> bytesRx{0};     // 接收字节数
    std::atomic<uint64_t> bytesTx{0};     // 发送字节数
    std::atomic<uint64_t> errorsRx{0};    // 接收错误数
    std::atomic<uint64_t> pingSent{0};    // 心跳发送
    std::atomic<uint64_t> pongReceived{0};// 心跳应答
    std::atomic<uint64_t> timeouts{0};    // 超时次数

    /// 重置所有统计
    void reset();

    /// 输出统计摘要
    std::string summary() const;
};

/// 心跳管理器
class HeartbeatManager {
public:
    HeartbeatManager();

    /// 心跳线程体（在独立线程中循环运行）
    /// @param writeFrameFn  发送帧的回调（通过 USB Bulk IN 发送）
    /// @param getStateFn    获取当前链路状态
    /// @param running       运行标志（主线程设 false 时退出）
    void run(
        std::function<int(const uint8_t*, int)> writeFrameFn,
        std::atomic<bool>& running
    );

    /// 收到 PONG 时调用（由 IO 线程检测到 Length=0 帧时调用）
    void onPongReceived();

    /// 获取链路状态
    LinkState linkState() const { return linkState_.load(); }

    /// 获取统计信息引用
    Stats& stats() { return stats_; }
    const Stats& stats() const { return stats_; }

    /// 上次收到对端帧的时间
    std::chrono::steady_clock::time_point lastRxTime() const;

private:
    std::atomic<LinkState> linkState_{LinkState::Disconnected};
    std::atomic<std::chrono::steady_clock::time_point::rep> lastPongTime_;
    Stats stats_;
};

} // namespace tun_nat

#endif // USB_TUND_HEARTBEAT_H
