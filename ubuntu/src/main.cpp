/**
 * main.cpp — TUN_NAT_HUB Ubuntu 守护进程 v4
 *
 *  2线程: TUN→TTY（含心跳） | TTY→TUN
 *  TTY 断线自动重连 — 等待 /dev/ttyGS0 重新出现并打开
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

/* ── 统计 ────────────────────────────────────────────────── */

struct Stats {
    std::atomic<uint64_t> tx{0};
    std::atomic<uint64_t> rx{0};
    std::atomic<uint64_t> txBytes{0};
    std::atomic<uint64_t> rxBytes{0};
    std::atomic<uint64_t> err{0};
    std::atomic<uint64_t> reconn{0};  // 重连次数
};

/* ── TTY 打开 ────────────────────────────────────────────── */

static int ttyOpen(const std::string& path, int waitSec) {
    for (int i = 0; i < waitSec; i++) {
        int fd = ::open(path.c_str(), O_RDWR | O_NOCTTY | O_NDELAY);
        if (fd >= 0) {
            int flags = fcntl(fd, F_GETFL, 0);
            fcntl(fd, F_SETFL, flags & ~O_NONBLOCK);
            struct termios tty = {};
            tcgetattr(fd, &tty);
            cfmakeraw(&tty);
            tty.c_cflag |= CLOCAL;
            tty.c_cc[VTIME] = 1;
            tty.c_cc[VMIN]  = 0;
            tcsetattr(fd, TCSANOW, &tty);
            std::cout << "[TTY] " << path << " 已打开 (fd=" << fd << ")" << std::endl;
            return fd;
        }
        if (errno != ENOENT && errno != ENODEV) break;
        if (i == 0) std::cerr << "[TTY] 等待 " << path << "..." << std::endl;
        sleep(1);
    }
    throw std::runtime_error("无法打开 " + path + ": " + strerror(errno));
}

/* ── TUN→TTY（含心跳，支持重连）──────────────────────────── */

static void tunToTtyThread(TunIface& tun, const std::string& ttyPath, Stats& stats) {
    std::cout << "[IO-TUN→TTY] 启动" << std::endl;

    uint8_t frameBuf[FRAME_MAX_LEN];
    uint8_t hb[FRAME_HEADER_LEN];
    frame_pack(hb, 0);

    while (gRunning) {
        // 打开或重连 TTY
        int fd = -1;
        while (gRunning) {
            try {
                fd = ttyOpen(ttyPath, 30);
                break;
            } catch (...) {
                stats.reconn++;
                sleep(2);
            }
        }
        if (!gRunning) break;

        auto lastHb = steady_clock::now();
        bool fdValid = true;

        // IO循环
        while (gRunning && fdValid) {
            int n = tun.readPacket(frameBuf + FRAME_HEADER_LEN, FRAME_MAX_PAYLOAD);
            if (n > 0) {
                int fl = frame_pack(frameBuf, n);
                if (::write(fd, frameBuf, fl) < 0) {
                    if (errno == EAGAIN) continue;
                    std::cerr << "[IO-TUN→TTY] write 错误: " << strerror(errno) << ", 重连..." << std::endl;
                    fdValid = false;
                    stats.reconn++;
                    continue;
                }
                stats.tx++; stats.txBytes += fl;
                lastHb = steady_clock::now();
            } else if (n < 0) {
                stats.err++; break;
            } else {
                // 无数据，发心跳
                auto now = steady_clock::now();
                if (duration_cast<milliseconds>(now - lastHb).count() >= 1000) {
                    if (::write(fd, hb, FRAME_HEADER_LEN) < 0) {
                        fdValid = false;
                        stats.reconn++;
                        continue;
                    }
                    stats.tx++; stats.txBytes += FRAME_HEADER_LEN;
                    lastHb = now;
                }
                usleep(5000);
            }
        }
        if (fd >= 0) ::close(fd);
    }
    std::cout << "[IO-TUN→TTY] 退出" << std::endl;
}

/* ── TTY→TUN（支持重连）──────────────────────────────────── */

static void ttyToTunThread(TunIface& tun, const std::string& ttyPath, Stats& stats) {
    std::cout << "[IO-TTY→TUN] 启动" << std::endl;

    uint8_t ring[FRAME_MAX_LEN * 2];
    int ringPos = 0;

    while (gRunning) {
        // 打开或重连 TTY
        int fd = -1;
        while (gRunning) {
            try {
                fd = ttyOpen(ttyPath, 30);
                break;
            } catch (...) {
                sleep(2);
            }
        }
        if (!gRunning) break;

        bool fdValid = true;
        while (gRunning && fdValid) {
            ssize_t n = ::read(fd, ring + ringPos, FRAME_MAX_LEN);
            if (n < 0) {
                if (errno == EAGAIN) continue;
                std::cerr << "[IO-TTY→TUN] read 错误: " << strerror(errno) << ", 重连..." << std::endl;
                fdValid = false;
                ringPos = 0;
                continue;
            }
            if (n == 0) { usleep(5000); continue; }

            ringPos += n;
            int off = 0;
            while (off + FRAME_HEADER_LEN <= ringPos) {
                uint8_t* p = nullptr;
                int pl = frame_unpack(ring + off, ringPos - off, &p);
                if (pl < 0) { if (pl == -1) off++; else break; continue; }

                if (frame_is_heartbeat(pl)) {
                    uint8_t pong[FRAME_HEADER_LEN];
                    frame_pack(pong, 0);
                    ::write(fd, pong, FRAME_HEADER_LEN);
                    off += FRAME_HEADER_LEN;
                    continue;
                }

                if (pl > 0) {
                    if (tun.writePacket(p, pl) < 0) stats.err++;
                    else { stats.rx++; stats.rxBytes += FRAME_HEADER_LEN + pl; }
                }
                off += FRAME_HEADER_LEN + pl;
            }
            if (off > 0 && off < ringPos) memmove(ring, ring + off, ringPos - off);
            ringPos -= off;
        }
        if (fd >= 0) ::close(fd);
    }
    std::cout << "[IO-TTY→TUN] 退出" << std::endl;
}

/* ── main ────────────────────────────────────────────────── */

int main(int argc, char* argv[]) {
    std::cout << "=== TUN_NAT_HUB v4 (auto-reconnect) ===" << std::endl;

    struct sigaction sa = {};
    sa.sa_handler = signalHandler;
    sigemptyset(&sa.sa_mask);
    sigaction(SIGTERM, &sa, nullptr);
    sigaction(SIGINT, &sa, nullptr);
    signal(SIGPIPE, SIG_IGN);

    std::string tunName = "tun_hub";
    std::string ttyPath = "/dev/ttyGS0";
    for (int i = 1; i < argc; i++) {
        std::string a = argv[i];
        if (a == "--tun" && i+1 < argc) tunName = argv[++i];
        else if (a == "--tty" && i+1 < argc) ttyPath = argv[++i];
    }

    try {
        TunIface tun(tunName);
        Stats stats;

        std::thread io1(tunToTtyThread, std::ref(tun), ttyPath, std::ref(stats));
        std::thread io2(ttyToTunThread, std::ref(tun), ttyPath, std::ref(stats));

        while (gRunning) {
            sleep(1);
            static int t = 0;
            if (++t % 5 == 0) {
                std::cout << "[统计] TX=" << stats.tx << "/" << stats.txBytes
                          << "B RX=" << stats.rx << "/" << stats.rxBytes
                          << "B err=" << stats.err << " reconn=" << stats.reconn << std::endl;
            }
        }

        tun.close();
        io1.join(); io2.join();
        std::cout << "=== 退出 (tx=" << stats.tx << " rx=" << stats.rx
                  << " reconn=" << stats.reconn << ") ===" << std::endl;
    } catch (const std::exception& e) {
        std::cerr << "[致命] " << e.what() << std::endl;
        return 1;
    }
    return 0;
}
