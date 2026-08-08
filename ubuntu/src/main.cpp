/**
 * main.cpp — TUN_NAT_HUB v5 (single-fd, auto-reconnect)
 *
 * 主线程打开 /dev/ttyGS0 → 二线程共享同一 fd
 * TTY 断开 → 主线程重开 fd → 线程继续
 */

#include "tun_iface.h"
#include <iostream>
#include <atomic>
#include <thread>
#include <csignal>
#include <cstring>
#include <string>
#include <unistd.h>
#include <fcntl.h>
#include <termios.h>
#include <errno.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>

extern "C" {
#include "frame.h"
}
using namespace tun_nat;

static std::atomic<bool> gRunning{true};
static std::atomic<int> gTtyFd{-1};

static void sigHandler(int s) { gRunning = false; }

struct Stats {
    std::atomic<uint64_t> tx{0}, rx{0}, txB{0}, rxB{0}, err{0};
};

/* ── TCP 延迟测试端口 (Android 端测隧道 RTT) ───────────── */
static void tcpPingServer() {
    int srv = socket(AF_INET, SOCK_STREAM, 0);
    if (srv < 0) { std::cerr << "[PING] socket failed" << std::endl; return; }
    int one = 1;
    setsockopt(srv, SOL_SOCKET, SO_REUSEADDR, &one, sizeof(one));

    struct sockaddr_in addr = {};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(9999);
    inet_pton(AF_INET, "10.0.0.1", &addr.sin_addr);
    if (bind(srv, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
        std::cerr << "[PING] bind 10.0.0.1:9999 failed: " << strerror(errno) << std::endl;
        close(srv); return;
    }
    if (listen(srv, 8) < 0) { perror("listen"); close(srv); return; }
    std::cout << "[PING] TCP 延迟测试端口 10.0.0.1:9999" << std::endl;

    // C5: accept 设置 1s 超时, 周期性返回检查 gRunning, 避免 SIGTERM 后无法 join
    struct timeval accTv;
    accTv.tv_sec = 1; accTv.tv_usec = 0;
    ::setsockopt(srv, SOL_SOCKET, SO_RCVTIMEO, &accTv, sizeof(accTv));

    while (gRunning) {
        int cli = accept(srv, nullptr, nullptr);
        if (cli >= 0) { close(cli); continue; }  // 只测 TCP 握手 RTT，不接受数据
        // 超时返回 (EAGAIN/EINTR) → 循环重新检查 gRunning
        if (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR) continue;
        // 硬错误 (EBADF/ENOTSOCK) → 退出, 避免死循环吃满 CPU
        break;
    }
    close(srv);
}

static int ttyOpen(const std::string& path) {
    for (int i = 0; i < 30 && gRunning; i++) {
        int fd = ::open(path.c_str(), O_RDWR | O_NOCTTY | O_NDELAY);
        if (fd >= 0) {
            fcntl(fd, F_SETFL, fcntl(fd, F_GETFL) & ~O_NONBLOCK);
            struct termios t = {};
            tcgetattr(fd, &t);
            cfmakeraw(&t);
            t.c_cflag |= CLOCAL;
            t.c_cc[VTIME] = 0;  // 立即返回，不等待（低延迟）
            t.c_cc[VMIN]  = 0;  // 有数据就返回
            tcsetattr(fd, TCSANOW, &t);
            return fd;
        }
        if (errno != ENOENT && errno != ENODEV) break;
        if (i == 0) std::cerr << "[TTY] 等待 " << path << std::endl;
        sleep(1);
    }
    return -1;
}

/* ── TUN→TTY（含心跳）───────────────────────────────────── */

static void tunToTty(TunIface& tun, Stats& s) {
    uint8_t buf[FRAME_MAX_LEN], hb[FRAME_HEADER_LEN];
    frame_pack(hb, 0);
    auto lastHb = std::chrono::steady_clock::now();

    while (gRunning) {
        int fd = gTtyFd.load();
        if (fd < 0) { usleep(10000); continue; }

        int n = tun.readPacket(buf + FRAME_HEADER_LEN, FRAME_MAX_PAYLOAD);
        if (n > 0) {
            int fl = frame_pack(buf, n);
            if (::write(fd, buf, fl) < 0 && errno != EAGAIN) {
                std::cerr << "[TUN→TTY] write err, fd=" << fd << std::endl;
                // CAS: 只有 fd 还是当前值时才置-1并关闭，避免抢占主线程重连的新 fd
                int expected = fd;
                if (gTtyFd.compare_exchange_strong(expected, -1)) ::close(fd);
                continue;
            }
            s.tx++; s.txB += fl;
            lastHb = std::chrono::steady_clock::now();
        } else if (n < 0) { s.err++; break; }
        else {
            auto now = std::chrono::steady_clock::now();
            if (std::chrono::duration_cast<std::chrono::milliseconds>(now - lastHb).count() >= 1000) {
                if (::write(fd, hb, FRAME_HEADER_LEN) < 0 && errno != EAGAIN) {
                    int expected = fd;
                    if (gTtyFd.compare_exchange_strong(expected, -1)) ::close(fd);
                    continue;
                }
                s.tx++; s.txB += FRAME_HEADER_LEN;
                lastHb = now;
            }
            usleep(1000);
        }
    }
}

/* ── TTY→TUN ────────────────────────────────────────────── */

static void ttyToTun(TunIface& tun, Stats& s) {
    uint8_t ring[FRAME_MAX_LEN * 2];
    int pos = 0;

    while (gRunning) {
        int fd = gTtyFd.load();
        if (fd < 0) { usleep(100000); pos = 0; continue; }

        ssize_t n = ::read(fd, ring + pos, FRAME_MAX_LEN);
        if (n < 0) {
            if (errno == EAGAIN) continue;
            std::cerr << "[TTY→TUN] read err, fd=" << fd << std::endl;
            int expected = fd;
            if (gTtyFd.compare_exchange_strong(expected, -1)) ::close(fd);
            pos = 0;
            continue;
        }
        if (n == 0) { usleep(1000); continue; }

        pos += n;
        int off = 0;
        while (off + FRAME_HEADER_LEN <= pos) {
            uint8_t* p = nullptr;
            int pl = frame_unpack(ring + off, pos - off, &p);
            if (pl < 0) { if (pl == -1) off++; else break; continue; }
            if (frame_is_heartbeat(pl)) {
                uint8_t pong[FRAME_HEADER_LEN];
                frame_pack(pong, 0);
                if (::write(fd, pong, FRAME_HEADER_LEN) < 0 && errno != EAGAIN) {
                    int expected = fd;
                    if (gTtyFd.compare_exchange_strong(expected, -1)) ::close(fd);
                    pos = 0;
                }
                off += FRAME_HEADER_LEN;
                continue;
            }
            if (pl > 0) {
                if (tun.writePacket(p, pl) < 0) s.err++;
                else { s.rx++; s.rxB += FRAME_HEADER_LEN + pl; }
            }
            off += FRAME_HEADER_LEN + pl;
        }
        if (off > 0 && off < pos) memmove(ring, ring + off, pos - off);
        pos -= off;
    }
}

/* ── main ────────────────────────────────────────────────── */

int main(int argc, char* argv[]) {
    std::cout << "=== TUN_NAT_HUB v5 ===" << std::endl;

    signal(SIGTERM, sigHandler); signal(SIGINT, sigHandler); signal(SIGPIPE, SIG_IGN);

    std::string tunName = "tun_hub", ttyPath = "/dev/ttyGS0";
    for (int i = 1; i < argc; i++) {
        std::string a = argv[i];
        if (a == "--tun" && i+1 < argc) tunName = argv[++i];
        else if (a == "--tty" && i+1 < argc) ttyPath = argv[++i];
    }

    try {
        TunIface tun(tunName);
        Stats stats;

        // 打开初始 TTY
        int fd = ttyOpen(ttyPath);
        if (fd < 0) throw std::runtime_error("无法打开 " + ttyPath);
        gTtyFd.store(fd);

        std::thread t1(tunToTty, std::ref(tun), std::ref(stats));
        std::thread t2(ttyToTun, std::ref(tun), std::ref(stats));
        std::thread t3(tcpPingServer);

        // 主循环: 监控 TTY fd 并自动重连
        int tick = 0;
        while (gRunning) {
            sleep(1);
            tick++;

            // 检测断线并重连
            if (gTtyFd.load() < 0) {
                std::cout << "[主] TTY 断开，重连中..." << std::endl;
                fd = ttyOpen(ttyPath);
                if (fd >= 0) {
                    gTtyFd.store(fd);
                    std::cout << "[主] TTY 重连成功 fd=" << fd << std::endl;
                }
            }

            if (tick % 5 == 0) {
                std::cout << "[统计] TX=" << stats.tx << "/" << stats.txB
                          << "B RX=" << stats.rx << "/" << stats.rxB
                          << "B err=" << stats.err << std::endl;
            }
        }

        // 关闭顺序: TUN readPacket 是阻塞读, 必须先 close 唤醒阻塞的线程再 join (否则 join 永久等待)
        tun.close();
        if (fd >= 0) ::close(fd);
        t1.join(); t2.join(); t3.join();
    } catch (const std::exception& e) {
        std::cerr << "[致命] " << e.what() << std::endl;
        return 1;
    }
    return 0;
}
