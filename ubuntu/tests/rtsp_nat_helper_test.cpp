#include "rtsp_nat_helper.h"

#include <cassert>
#include <string>
#include <vector>

int main() {
    assert(rtspHostFromUrl("rtsp://192.168.144.31:554/stream1") == "192.168.144.31");
    assert(rtspHostFromUrl("rtsp://user:pass@192.168.144.31/live") == "192.168.144.31");
    assert(rtspHostFromUrl("rtsp://192.168.144.31") == "192.168.144.31");
    assert(rtspHostFromUrl("http://192.168.144.31/stream1").empty());

    assert(isIpv4Literal("192.168.144.31"));
    assert(!isIpv4Literal("cam.local"));
    assert(!isIpv4Literal("999.168.144.31"));

    std::vector<std::string> hosts;
    addUniqueIpv4Host(hosts, rtspHostFromUrl("rtsp://192.168.144.31:554/stream1"));
    addUniqueIpv4Host(hosts, rtspHostFromUrl("rtsp://user:pass@192.168.144.31/live"));
    addUniqueIpv4Host(hosts, rtspHostFromUrl("rtsp://cam.local/live"));
    assert(hosts.size() == 1);
    assert(hosts[0] == "192.168.144.31");

    return 0;
}
