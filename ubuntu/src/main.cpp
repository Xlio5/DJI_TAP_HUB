/**
 * main.cpp — TUN_NAT_HUB Ubuntu 守护进程 v2
 *
 * 使用 CDC ACM Gadget (/dev/ttyGS0) 替代 FunctionFS。
 * CDC ACM 提供 2 个 Bulk 端点，内核自动处理 USB 枚举。
 *
 * 架构: 3 线程
 *   主线程:      信号处理 + 等待退出
 *   IO-Thread-1: TUN → USB (read TUN → framePack → write ttyGS0)
 *   IO-Thread-2: USB → TUN (read ttyGS0 → frameUnpack → write TUN)
 *
 * 信号: SIGTERM/SIGINT → running = false → 优雅退出
 */

#include "tun_iface.h"

#include <iostream>
#include <atomic>
#include <thread>
#include <csignal>
#include <cstring>
#include <string>
#include <functional>

#include <unistd.h>
#include <fcntl.h>
#include <termios.h>
#include <errno.h>

extern "C" {
#include "frame.h"
}

using namespace tun_nat;

static std::atomic<bool> gRunning{true};

static void signalHandler(int sig) {
    std::cout << "\n[信号] 收到信号 " << sig << "，正在退出..." << std::endl;
    gRunning = false;
}

// 统计
struct Stats {
    std::atomic<uint64_t> framesRx{0};
    std::atomic<uint64_t> framesTx{0};
    std::atomic<uint64_t> bytesRx{0};
    std::atomic<uint64_t> bytesTx{0};
    std::atomic<uint64_t> errors{0};
};

// 打开 TTY 并设为 raw 模式
static int openTtyRaw(const std::string& path) {
    int fd = ::open(path.c_str(), O_RDWR | O_NOCTTY | O_NDELAY);
    if (fd < 0) {
        throw std::runtime_error("无法打开 " + path + ": " + strerror(errno));
    }

    // 设为阻塞模式
    int flags = fcntl(fd, F_GETFL, 0);
    fcntl(fd, F_SETFL, flags & ~O_NONBLOCK);

    struct termios tty = {};
    if (tcgetattr(fd, &tty) != 0) {
        ::close(fd);
        throw std::runtime_error("tcgetattr 失败: " + std::string(strerror(errno)));
    }

    // Raw 模式: 无行处理、无回显、无信号字符
    cfmakeraw(&tty);
    tty.c_cc[VTIME] = 1;    // 100ms 超时
    tty.c_cc[VMIN]  = 0;    // 非阻塞式读取

    if (tcsetattr(fd, TCSANOW, &tty) != 0) {
        ::close(fd);
        throw std::runtime_error("tcsetattr 失败: " + std::string(strerror(errno)));
    }

    std::cout << "[TTY] " << path << " 已打开 (fd=" << fd << ")" << std::endl;
    return fd;
}

/* ── IO Thread 1: TUN → TTY (出向) ──────────────────────────── */

static void tunToTtyThread(TunIface& tun, int ttyFd, Stats& stats) {
    std::cout << "[IO-TUN→TTY] 线程启动" << std::endl;
    uint8_t frameBuf[FRAME_MAX_LEN];

    while (gRunning) {
        int n = tun.readPacket(frameBuf + FRAME_HEADER_LEN, FRAME_MAX_PAYLOAD);
        if (n < 0) { stats.errors++; break; }
        if (n == 0) { usleep(1000); continue; }

        int frameLen = frame_pack(frameBuf, n);
        ssize_t w = ::write(ttyFd, frameBuf, frameLen);

        if (w < 0) {
            if (errno == EAGAIN) continue;
            std::cerr << "[IO-TUN→TTY] write 错误: " << strerror(errno) << std::endl;
            stats.errors++;
            break;
        }
        stats.framesTx++;
        stats.bytesTx += frameLen;
    }
    std::cout << "[IO-TUN→TTY] 线程退出" << std::endl;
}

/* ── IO Thread 2: TTY → TUN (入向) ──────────────────────────── */

static void ttyToTunThread(TunIface& tun, int ttyFd, Stats& stats) {
    std::cout << "[IO-TTY→TUN] 线程启动" << std::endl;
    uint8_t frameBuf[FRAME_MAX_LEN];

    // 环形缓冲区用于帧同步恢复
    uint8_t ringBuf[FRAME_MAX_LEN * 2];
    int ringPos = 0;

    while (gRunning) {
        ssize_t n = ::read(ttyFd, ringBuf + ringPos, FRAME_MAX_LEN - ringPos);
        if (n < 0) {
            if (errno == EAGAIN) continue;
            std::cerr << "[IO-TTY→TUN] read 错误: " << strerror(errno) << std::endl;
            stats.errors++;
            break;
        }
        if (n == 0) { usleep(1000); continue; }

        ringPos += n;

        // 处理缓冲区中的所有完整帧
        int consumed = 0;
        while (consumed + FRAME_HEADER_LEN <= ringPos) {
            uint8_t* p = nullptr;
            int payloadLen = frame_unpack(ringBuf + consumed, ringPos - consumed, &p);
            if (payloadLen < 0) {
                // 帧同步失败: 跳过当前字节重试
                if (payloadLen == -1) {  // magic mismatch
                    consumed++;
                    continue;
                }
                break;  // 帧不完整，等更多数据
            }

            // 心跳帧
            if (frame_is_heartbeat(payloadLen)) {
                // 回 PONG
                uint8_t pong[FRAME_HEADER_LEN];
                frame_pack(pong, 0);
                ::write(ttyFd, pong, FRAME_HEADER_LEN);
                consumed += FRAME_HEADER_LEN;
                continue;
            }

            // 正常数据帧
            int written = tun.writePacket(p, payloadLen);
            if (written < 0) {
                stats.errors++;
            } else {
                stats.framesRx++;
                stats.bytesRx += FRAME_HEADER_LEN + payloadLen;
            }
            consumed += FRAME_HEADER_LEN + payloadLen;
        }

        // 移动剩余数据到缓冲区开头
        if (consumed > 0 && consumed < ringPos) {
            memmove(ringBuf, ringBuf + consumed, ringPos - consumed);
        }
        ringPos -= consumed;
    }
    std::cout << "[IO-TTY→TUN] 线程退出" << std::endl;
}

/* ── main ───────────────────────────────────────────────────── */

int main(int argc, char* argv[]) {
    std::cout << "=== TUN_NAT_HUB 守护进程 v2 (ACM) ===" << std::endl;

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
        std::cout << "\n=== 启动 IO 线程 ===" << std::endl;

        std::thread io1(tunToTtyThread, std::ref(tun), ttyFd, std::ref(stats));
        std::thread io2(ttyToTunThread, std::ref(tun), ttyFd, std::ref(stats));

        while (gRunning) {
            sleep(5);
            std::cout << "[统计] TX=" << stats.framesTx
                      << " frames/" << stats.bytesTx
                      << "B RX=" << stats.framesRx
                      << " frames/" << stats.bytesRx
                      << "B err=" << stats.errors << std::endl;
        }

        std::cout << "\n=== 退出... ===" << std::endl;
        tun.close();
        ::close(ttyFd);

        io1.join();
        io2.join();

        std::cout << "=== 守护进程已退出 ===" << std::endl;
    } catch (const std::exception& e) {
        std::cerr << "[致命错误] " << e.what() << std::endl;
        return 1;
    }
    return 0;
}
