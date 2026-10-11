#pragma once

#include <chrono>
#include <condition_variable>
#include <cstdint>
#include <mutex>

enum class RcEventWait {
    Timeout,
    Changed,
    Stopped,
};

class RcEventGate {
public:
    uint64_t generation() const;
    void notify();
    RcEventWait waitForChange(uint64_t observed,
                              std::chrono::milliseconds timeout,
                              uint64_t *current);
    void stop();

private:
    mutable std::mutex mutex_;
    std::condition_variable condition_;
    uint64_t generation_ = 0;
    bool stopped_ = false;
};
