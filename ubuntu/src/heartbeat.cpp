/**
 * heartbeat.cpp — 心跳保活实现
 */

#include "heartbeat.h"
#include "frame.h"

#include <iostream>
#include <sstream>
#include <thread>
#include <cstring>

namespace tun_nat {

/* ── Stats ─────────────────────────────────────────────────── */

void Stats::reset() {
    framesRx = 0;
    framesTx = 0;
    bytesRx = 0;
    bytesTx = 0;
    errorsRx = 0;
    pingSent = 0;
    pongReceived = 0;
    timeouts = 0;
}

std::string Stats::summary() const {
    std::ostringstream oss;
    oss << "RX frames=" << framesRx
        << " bytes=" << bytesRx
        << " | TX frames=" << framesTx
        << " bytes=" << bytesTx
        << " | errors=" << errorsRx
        << " | ping=" << pingSent
        << " pong=" << pongReceived
        << " timeouts=" << timeouts;
    return oss.str();
}

/* ── HeartbeatManager ──────────────────────────────────────── */

HeartbeatManager::HeartbeatManager() {
    // 用当前时间初始化
    auto now = std::chrono::steady_clock::now();
    lastPongTime_ = now.time_since_epoch().count();
}

void HeartbeatManager::onPongReceived() {
    auto now = std::chrono::steady_clock::now();
    lastPongTime_ = now.time_since_epoch().count();
    stats_.pongReceived++;

    // 收到 PONG → 链路健康
    auto expected = LinkState::Disconnected;
    linkState_.compare_exchange_strong(expected, LinkState::Connected);
}

std::chrono::steady_clock::time_point HeartbeatManager::lastRxTime() const {
    auto dur = std::chrono::steady_clock::duration(lastPongTime_.load());
    return std::chrono::steady_clock::time_point(dur);
}

void HeartbeatManager::run(
    std::function<int(const uint8_t*, int)> writeFrameFn,
    std::atomic<bool>& running)
{
    // PING 帧: 4 字节帧头 + 0 字节 payload（Length=0）
    uint8_t pingFrame[FRAME_HEADER_LEN];
    frame_pack(pingFrame, 0);  // Length=0 → 心跳帧

    auto lastPingTime = std::chrono::steady_clock::now();

    while (running) {
        std::this_thread::sleep_for(std::chrono::milliseconds(100));

        auto now = std::chrono::steady_clock::now();

        // 每 1000ms 发送 PING
        auto sinceLastPing = std::chrono::duration_cast<std::chrono::milliseconds>(
            now - lastPingTime).count();

        if (sinceLastPing >= HEARTBEAT_INTERVAL_MS) {
            // 发送 PING
            int ret = writeFrameFn(pingFrame, FRAME_HEADER_LEN);
            if (ret > 0) {
                stats_.pingSent++;
            }
            lastPingTime = now;

            // 检查超时（3000ms 无 PONG）
            auto lastPongTp = lastRxTime();
            auto sinceLastPong = std::chrono::duration_cast<std::chrono::milliseconds>(
                now - lastPongTp).count();

            if (sinceLastPong > HEARTBEAT_TIMEOUT_UBUNTU && linkState_ != LinkState::Disconnected) {
                std::cerr << "[心跳] 超时 " << sinceLastPong << "ms 无 PONG，链路断开" << std::endl;
                linkState_ = LinkState::Disconnected;
                stats_.timeouts++;
            }
        }
    }
}

} // namespace tun_nat
