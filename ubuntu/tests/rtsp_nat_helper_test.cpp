#include "rtsp_nat_helper.h"

#include <iostream>
#include <string>
#include <vector>

static int failures = 0;

static void expectTrue(bool value, const char* message) {
    if (!value) {
        std::cerr << "FAIL: " << message << "\n";
        failures++;
    }
}

static void expectEqual(const std::string& actual, const std::string& expected, const char* message) {
    if (actual != expected) {
        std::cerr << "FAIL: " << message << ": expected " << expected << ", got " << actual << "\n";
        failures++;
    }
}

int main() {
    expectEqual(rtspHostFromUrl("rtsp://192.168.144.31:554/stream1"), "192.168.144.31", "plain RTSP host");
    expectEqual(rtspHostFromUrl("rtsp://user:pass@192.168.144.31/live"), "192.168.144.31", "RTSP host with auth");
    expectEqual(rtspHostFromUrl("rtsp://192.168.144.31"), "192.168.144.31", "RTSP host without path");
    expectTrue(rtspHostFromUrl("http://192.168.144.31/stream1").empty(), "reject non-RTSP URL");

    expectTrue(isIpv4Literal("192.168.144.31"), "accept IPv4 literal");
    expectTrue(!isIpv4Literal("cam.local"), "reject DNS host");
    expectTrue(!isIpv4Literal("999.168.144.31"), "reject out-of-range IPv4");

    std::vector<std::string> hosts;
    addUniqueIpv4Host(hosts, rtspHostFromUrl("rtsp://192.168.144.31:554/stream1"));
    addUniqueIpv4Host(hosts, rtspHostFromUrl("rtsp://user:pass@192.168.144.31/live"));
    addUniqueIpv4Host(hosts, rtspHostFromUrl("rtsp://cam.local/live"));
    expectTrue(hosts.size() == 1, "dedupe IPv4 RTSP hosts");
    if (!hosts.empty()) {
        expectEqual(hosts[0], "192.168.144.31", "first deduped RTSP host");
    }

    expectEqual(rtspForwardTarget(), "10.0.0.2", "RTSP RTP DNAT target");

    return failures == 0 ? 0 : 1;
}
