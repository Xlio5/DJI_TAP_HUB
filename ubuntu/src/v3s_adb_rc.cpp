#include "adb_client.h"
#include "adb_getevent_rc.h"

#include <cerrno>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>

#include <time.h>

namespace {

volatile sig_atomic_t g_stop = 0;

void on_signal(int)
{
    g_stop = 1;
}

int64_t monotonic_ms()
{
    timespec ts{};
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (int64_t)ts.tv_sec * 1000LL + ts.tv_nsec / 1000000LL;
}

void usage(const char *argv0)
{
    std::fprintf(stderr,
                 "用法: %s [--host 10.0.0.2] [--port 5555] [--device /dev/input/event4]\n"
                 "          [--seconds 10] [--command \"getprop ro.product.model; id\"]\n",
                 argv0);
}

void print_state(const rc_state_t &st, uint32_t events, int64_t elapsed_ms)
{
    double hz = elapsed_ms > 0 ? (events * 1000.0 / elapsed_ms) : 0.0;
    std::printf("events=%u hz=%.1f ch=[%d,%d,%d,%d,%d,%d] mode=%c\n",
                events, hz,
                st.ch[0], st.ch[1], st.ch[2], st.ch[3], st.ch[4], st.ch[5],
                st.mode ? st.mode : '?');
    std::fflush(stdout);
}

}  // namespace

int main(int argc, char **argv)
{
    AdbClientOptions opt;
    std::string device = "/dev/input/event4";
    std::string command;
    int seconds = 10;

    for (int i = 1; i < argc; i++) {
        if (std::strcmp(argv[i], "--host") == 0 && i + 1 < argc) {
            opt.host = argv[++i];
        } else if (std::strcmp(argv[i], "--port") == 0 && i + 1 < argc) {
            opt.port = (uint16_t)std::atoi(argv[++i]);
        } else if (std::strcmp(argv[i], "--device") == 0 && i + 1 < argc) {
            device = argv[++i];
        } else if (std::strcmp(argv[i], "--seconds") == 0 && i + 1 < argc) {
            seconds = std::atoi(argv[++i]);
        } else if (std::strcmp(argv[i], "--command") == 0 && i + 1 < argc) {
            command = argv[++i];
        } else if (std::strcmp(argv[i], "--help") == 0) {
            usage(argv[0]);
            return 0;
        } else {
            usage(argv[0]);
            return 2;
        }
    }

    std::signal(SIGINT, on_signal);
    std::signal(SIGTERM, on_signal);
    std::signal(SIGPIPE, SIG_IGN);

    AdbClient adb;
    std::string error;
    if (!adb.connect(opt, &error)) {
        std::fprintf(stderr, "ADB connect %s:%u failed: %s\n",
                     opt.host.c_str(), opt.port, error.c_str());
        return 1;
    }

    std::string shell = command.empty() ? ("getevent -lt " + device) : command;
    if (!adb.openShell(shell, &error)) {
        std::fprintf(stderr, "ADB shell open failed: %s\n", error.c_str());
        return 1;
    }

    int64_t start = monotonic_ms();
    int64_t last_print = start;
    std::string linebuf;
    rc_state_t state{};
    state.type = RC_APP_FUSED;
    state.mode = '?';
    uint32_t events = 0;
    bool closed = false;

    while (!g_stop && !closed) {
        int64_t now = monotonic_ms();
        if (seconds > 0 && now - start >= (int64_t)seconds * 1000LL) break;

        std::string chunk;
        if (!adb.readShellChunk(&chunk, &closed, &error)) {
            std::fprintf(stderr, "ADB shell read failed: %s\n", error.c_str());
            return 1;
        }
        if (chunk.empty()) {
            if (command.empty() && now - last_print >= 1000) {
                print_state(state, events, now - start);
                last_print = now;
            }
            continue;
        }
        if (!command.empty()) {
            std::fwrite(chunk.data(), 1, chunk.size(), stdout);
            std::fflush(stdout);
            continue;
        }

        linebuf.append(chunk);
        size_t pos;
        while ((pos = linebuf.find('\n')) != std::string::npos) {
            std::string line = linebuf.substr(0, pos);
            linebuf.erase(0, pos + 1);
            GeteventAbsEvent ev;
            if (parse_getevent_abs_line(line, &ev) && apply_getevent_axis(ev, device, &state)) {
                events++;
            }
        }
        now = monotonic_ms();
        if (now - last_print >= 250) {
            print_state(state, events, now - start);
            last_print = now;
        }
    }

    if (command.empty()) print_state(state, events, monotonic_ms() - start);
    return 0;
}
