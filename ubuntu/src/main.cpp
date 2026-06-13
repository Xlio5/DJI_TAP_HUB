/**
 * main.cpp — TUN_NAT_HUB Ubuntu 守护进程 v3
 *
 * 优化: 心跳合并到 TUN→TTY 线程（省一个线程），epoll 替代 busy-wait
 *
 * 架构: 2 线程
 *   主线程: 信号处理 + 统计输出
 *   IO-1:   TUN → TTY（含心跳: 1 秒无数据自动发 PING）
 *   IO-2:   TTY → TUN
 */

#include "tun_iface.h"

#include <iostream>
#include <atomic>
#include <thread>
#include <csignal>
#include <cstring>
#include <string>
#include <chrono>

#include <unistd.h>
#include <fcntl.h>
#include <termios.h>
#include <errno.h>
#include <sys/epoll.h>

extern "C" {
#include "frame.h"
}

using namespace tun_nat;
using namespace std::chrono;

static std::atomic<bool> gRunning{true};

static void signalHandler(int sig) {
    std::cout << "\n[信号] 收到信号 " << sig << "，正在退出..." << std::endl;
    gRunning = false;
}

struct Stats {
    std::atomic<uint64_t> framesRx{0};
    std::atomic<uint64_t> framesTx{0};
    std::atomic<uint64_t> bytesRx{0};
    std::atomic<uint64_t> bytesTx{0};
    std::atomic<uint64_t> errors{0};
};

// 打开 TTY 并设为 raw 模式（可等待设备出现）
static int openTtyRaw(const std::string& path) {
    int fd = -1;
    for (int retry = 0; retry < 30; retry++) {
        fd = ::open(path.c_str(), O_RDWR | O_NOCTTY | O_NDELAY);
        if (fd >= 0) break;
        if (errno != ENOENT && errno != ENODEV) {
            throw std::runtime_error("无法打开 " + path + ": " + strerror(errno));
        }
        std::cerr << "[TTY] 等待 " << path << " 出现... (" << (retry + 1) << "/30)" << std::endl;
        sleep(1);
    }
    if (fd < 0) {
        throw std::runtime_error("无法打开 " + path + " (等待 30s 后仍不存在): " + strerror(errno));
    }

    int flags = fcntl(fd, F_GETFL, 0);
    fcntl(fd, F_SETFL, flags & ~O_NONBLOCK);

    struct termios tty = {};
    if (tcgetattr(fd, &tty) != 0) {
        ::close(fd);
        throw std::runtime_error("tcgetattr 失败: " + std::string(strerror(errno)));
    }

    cfmakeraw(&tty);
    tty.c_cflag |= CLOCAL;
    tty.c_cc[VTIME] = 1;
    tty.c_cc[VMIN]  = 0;

    if (tcsetattr(fd, TCSANOW, &tty) != 0) {
        ::close(fd);
        throw std::runtime_error("tcsetattr 失败: " + std::string(strerror(errno)));
    }

    std::cout << "[TTY] " << path << " 已打开 (fd=" << fd << ")" << std::endl;
    return fd;
}

/* ── IO Thread 1: TUN → TTY（含心跳） ──────────────────────── */

static void tunToTtyThread(TunIface& tun, int ttyFd, Stats& stats) {
    std::cout << "[IO-TUN→TTY] 线程启动（含心跳）" << std::endl;
    uint8_t frameBuf[FRAME_MAX_LEN];
    uint8_t hbFrame[FRAME_HEADER_LEN];
    frame_pack(hbFrame, 0); // 预建心跳帧

    auto lastHb = steady_clock::now();

    while (gRunning) {
        int n = tun.readPacket(frameBuf + FRAME_HEADER_LEN, FRAME_MAX_PAYLOAD);

        if (n > 0) {
            int frameLen = frame_pack(frameBuf, n);
            ssize_t w = ::write(ttyFd, frameBuf, frameLen);
            if (w < 0) {
                if (errno == EAGAIN) continue;
                std::cerr << "[IO-TUN→TTY] write 错误: " << strerror(errno) << std::endl;
                stats.errors++; break;
            }
            stats.framesTx++;
            stats.bytesTx += frameLen;
            lastHb = steady_clock::now(); // 有数据流过，重置心跳计时器
        } else if (n < 0) {
            stats.errors++; break;
        } else {
            // n == 0: TUN 无数据，检查是否需要发心跳
            auto now = steady_clock::now();
            if (duration_cast<milliseconds>(now - lastHb).count() >= 1000) {
                ::write(ttyFd, hbFrame, FRAME_HEADER_LEN);
                stats.framesTx++;
                stats.bytesTx += FRAME_HEADER_LEN;
                lastHb = now;
            }
            usleep(50000); // 50ms 粒度，避免 CPU 空转
        }
    }
    std::cout << "[IO-TUN→TTY] 线程退出" << std::endl;
}

/* ── IO Thread 2: TTY → TUN ─────────────────────────────────── */

static void ttyToTunThread(TunIface& tun, int ttyFd, Stats& stats) {
    std::cout << "[IO-TTY→TUN] 线程启动" << std::endl;

    uint8_t ringBuf[FRAME_MAX_LEN * 2];
    int ringPos = 0;

    while (gRunning) {
        ssize_t n = ::read(ttyFd, ringBuf + ringPos, FRAME_MAX_LEN - ringPos);
        if (n < 0) {
            if (errno == EAGAIN) continue;
            std::cerr << "[IO-TTY→TUN] read 错误: " << strerror(errno) << std::endl;
            stats.errors++; break;
        }
        if (n == 0) { usleep(50000); continue; }  // 50ms yield

        ringPos += n;

        int consumed = 0;
        while (consumed + FRAME_HEADER_LEN <= ringPos) {
            uint8_t* p = nullptr;
            int payloadLen = frame_unpack(ringBuf + consumed, ringPos - consumed, &p);
            if (payloadLen < 0) {
                if (payloadLen == -1) { consumed++; continue; }
                break;  // 帧不完整，等更多数据
            }

            if (frame_is_heartbeat(payloadLen)) {
                // 回 PONG
                uint8_t pong[FRAME_HEADER_LEN];
                frame_pack(pong, 0);
                ::write(ttyFd, pong, FRAME_HEADER_LEN);
                consumed += FRAME_HEADER_LEN;
                continue;
            }

            if (frame_is_credit(payloadLen)) {
                consumed += FRAME_HEADER_LEN + payloadLen;
                continue;
            }

            int written = tun.writePacket(p, payloadLen);
            if (written < 0) { stats.errors++; }
            else { stats.framesRx++; stats.bytesRx += FRAME_HEADER_LEN + payloadLen; }
            consumed += FRAME_HEADER_LEN + payloadLen;
        }

        if (consumed > 0 && consumed < ringPos) {
            memmove(ringBuf, ringBuf + consumed, ringPos - consumed);
        }
        ringPos -= consumed;
    }
    std::cout << "[IO-TTY→TUN] 线程退出" << std::endl;
}

/* ── main ───────────────────────────────────────────────────── */

int main(int argc, char* argv[]) {
    std::cout << "=== TUN_NAT_HUB 守护进程 v3 ===" << std::endl;

    struct sigaction sa = {};
    sa.sa_handler = signalHandler;
    sigemptyset(&sa.sa_mask);
    sigaction(SIGTERM, &sa, nullptr);
    sigaction(SIGINT, &sa, nullptr);
    signal(SIGPIPE, SIG_IGN);

    std::string tunName = "tun_hub";
    std::string ttyPath = "/dev/ttyGS0";

    for (int i = 1; i < argc; i++) {
        std::string arg = argv[i];
        if (arg == "--tun" && i + 1 < argc) tunName = argv[++i];
        else if (arg == "--tty" && i + 1 < argc) ttyPath = argv[++i];
        else if (arg == "--help" || arg == "-h") {
            std::cout << "用法: usb_tund [--tun NAME] [--tty PATH]\n";
            return 0;
        }
    }

    try {
        std::cout << "\n--- TUN 接口 ---" << std::endl;
        TunIface tun(tunName);

        std::cout << "\n--- TTY 设备 ---" << std::endl;
        int ttyFd = openTtyRaw(ttyPath);

        Stats stats;
        std::cout << "\n=== 启动 IO 线程 === (2 threads)" << std::endl;

        std::thread io1(tunToTtyThread, std::ref(tun), ttyFd, std::ref(stats));
        std::thread io2(ttyToTunThread, std::ref(tun), ttyFd, std::ref(stats));

        // 主循环: 每秒检查退出标志（而非 5 秒阻塞）
        while (gRunning) {
            sleep(1);
            static int tick = 0;
            if (++tick % 5 == 0) {  // 每 5 秒输出统计
                std::cout << "[统计] TX=" << stats.framesTx
                          << "/" << stats.bytesTx
                          << "B RX=" << stats.framesRx
                          << "/" << stats.bytesRx
                          << "B err=" << stats.errors << std::endl;
            }
        }

        std::cout << "\n=== 退出... ===" << std::endl;
        tun.close();
        ::close(ttyFd);

        io1.join();
        io2.join();

        std::cout << "=== 守护进程已退出 (" << stats.framesTx
                  << " tx, " << stats.framesRx << " rx)" << std::endl;
    } catch (const std::exception& e) {
        std::cerr << "[致命错误] " << e.what() << std::endl;
        return 1;
    }
    return 0;
}
