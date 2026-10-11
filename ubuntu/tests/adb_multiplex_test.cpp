#include "adb_client.h"

#include <cstdio>
#include <cstdlib>
#include <string>

namespace {

void expect(bool condition, const char *message)
{
    if (!condition) {
        std::fprintf(stderr, "FAIL: %s\n", message);
        std::exit(1);
    }
}

AdbPacket packet(const char *command, uint32_t remote_id, uint32_t local_id,
                 const std::string &payload = {})
{
    AdbPacket result;
    result.command = adb_command(command);
    result.arg0 = remote_id;
    result.arg1 = local_id;
    result.payload.assign(payload.begin(), payload.end());
    return result;
}

}  // namespace

int main()
{
    AdbStreamMux mux;
    const uint32_t event4 = mux.allocateStream();
    const uint32_t event3 = mux.allocateStream();
    const uint32_t port40007 = mux.allocateStream();

    expect(event4 != event3 && event3 != port40007 && event4 != port40007,
           "每个 ADB stream 必须有唯一的本地 ID");

    AdbStreamEvent event;
    expect(mux.route(packet("OKAY", 41, event4), &event),
           "event4 OKAY 应被接受");
    expect(mux.route(packet("OKAY", 42, event3), &event),
           "event3 OKAY 应被接受");
    expect(mux.route(packet("OKAY", 43, port40007), &event),
           "40007 OKAY 应被接受");

    expect(mux.route(packet("WRTE", 42, event3, "key\n"), &event),
           "event3 WRTE 应被路由");
    expect(event.local_id == event3 && event.remote_id == 42 &&
               event.type == AdbStreamEventType::Data && event.data == "key\n",
           "交错数据必须归属 event3 stream");

    expect(mux.route(packet("WRTE", 41, event4, "axis\n"), &event),
           "event4 WRTE 应被路由");
    expect(event.local_id == event4 && event.remote_id == 41 &&
               event.type == AdbStreamEventType::Data && event.data == "axis\n",
           "交错数据必须归属 event4 stream");

    expect(mux.route(packet("CLSE", 42, event3), &event),
           "event3 CLSE 应被路由");
    expect(event.local_id == event3 && event.type == AdbStreamEventType::Closed,
           "关闭事件必须标记 event3");
    expect(mux.isOpen(event4), "关闭 event3 不得影响 event4");
    expect(!mux.isOpen(event3), "event3 应标记为关闭");
    expect(mux.isOpen(port40007), "关闭 event3 不得影响 40007");

    std::puts("adb_multiplex_test: PASS");
    return 0;
}
