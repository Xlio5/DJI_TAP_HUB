#include "rc_event_gate.h"

uint64_t RcEventGate::generation() const
{
    std::lock_guard<std::mutex> lock(mutex_);
    return generation_;
}

void RcEventGate::notify()
{
    {
        std::lock_guard<std::mutex> lock(mutex_);
        ++generation_;
    }
    condition_.notify_one();
}

RcEventWait RcEventGate::waitForChange(uint64_t observed,
                                       std::chrono::milliseconds timeout,
                                       uint64_t *current)
{
    std::unique_lock<std::mutex> lock(mutex_);
    bool ready = condition_.wait_for(lock, timeout, [&] {
        return stopped_ || generation_ != observed;
    });
    if (current) *current = generation_;
    if (stopped_) return RcEventWait::Stopped;
    return ready ? RcEventWait::Changed : RcEventWait::Timeout;
}

void RcEventGate::stop()
{
    {
        std::lock_guard<std::mutex> lock(mutex_);
        stopped_ = true;
    }
    condition_.notify_all();
}
