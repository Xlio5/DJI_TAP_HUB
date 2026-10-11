#include "rc_event_gate.h"

#include <chrono>
#include <cstdlib>
#include <iostream>
#include <thread>

static void expect(bool condition, const char *name)
{
    if (!condition) {
        std::cerr << "FAIL: " << name << '\n';
        std::exit(1);
    }
}

int main()
{
    using namespace std::chrono_literals;

    RcEventGate gate;
    uint64_t generation = gate.generation();
    expect(gate.waitForChange(generation, 2ms, &generation) == RcEventWait::Timeout,
           "unchanged generation times out");

    gate.notify();
    expect(gate.waitForChange(generation, 50ms, &generation) == RcEventWait::Changed,
           "new generation wakes immediately");

    RcEventWait stopped = RcEventWait::Timeout;
    std::thread waiter([&] {
        uint64_t observed = generation;
        stopped = gate.waitForChange(observed, 1s, &observed);
    });
    std::this_thread::sleep_for(5ms);
    gate.stop();
    waiter.join();
    expect(stopped == RcEventWait::Stopped, "stop wakes waiter");

    std::cout << "rc_event_gate_test PASS\n";
    return 0;
}
