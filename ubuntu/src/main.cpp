/**
 * main.cpp — TUN_NAT_HUB UDP 隧道 (WiFi + USB 通用)
 *
 * 创建 TUN + UDP socket，通过 WiFi 或 USB ECM/RNDIS 收发原始 IP 包。
 * 无需帧协议 — IP 包直接装入 UDP 数据报文。
 * 同时支持 WiFi (172.24.91.x) 和 USB (usb0/rndis0)。
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
#include <cerrno>

#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <sys/ioctl.h>
#include <net/if.h>

using namespace tun_nat;

static std::atomic<bool> gRunning{true};

static void sigHandler(int s) { gRunning = false; }

static constexpr int UDP_PORT         = 8899;
static constexpr int MAX_IP_PACKET    = 1500;
static constexpr int HB_INTERVAL_MS   = 1000;
static constexpr int HB_TIMEOUT_MS    = 5000;
static constexpr uint8_t HB_PING      = 0x00;
static constexpr uint8_t HB_PONG      = 0x01;

struct Stats {
    std::atomic<uint64_t> tx{0}, rx{0}, txB{0}, rxB{0}, err{0}, hb{0};
};

/**
 * 创建 UDP socket，绑定所有接口 (INADDR_ANY:8899)。
 * 同时支持 WiFi 和 USB ECM/RNDIS。
 */
static int udpBind() {
    int fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (fd < 0) {
        std::cerr << "[UDP] socket failed: " << strerror(errno) << std::endl;
        return -1;
    }
    int flags = fcntl(fd, F_GETFL, 0);
    fcntl(fd, F_SETFL, flags | O_NONBLOCK);
    int reuse = 1;
    setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse));

    struct sockaddr_in addr = {};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(UDP_PORT);
    addr.sin_addr.s_addr = htonl(INADDR_ANY);

    if (bind(fd, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
        std::cerr << "[UDP] bind failed: " << strerror(errno) << std::endl;
        close(fd);
        return -1;
    }
    std::cout << "[UDP] bound 0.0.0.0:" << UDP_PORT << " (fd=" << fd << ")" << std::endl;
    return fd;
}

/* ── TUN -> UDP ──────────────────────────────────────── */

static void tunToUdp(TunIface& tun, int udpFd, Stats& s,
                   const std::atomic<struct sockaddr_in*>& peerAddr,
                   const std::atomic<bool>& havePeer) {
    uint8_t buf[MAX_IP_PACKET];
    auto lastHb = std::chrono::steady_clock::now();

    while (gRunning) {
        int n = tun.readPacket(buf, sizeof(buf));
        if (n > 0) {
            if (havePeer.load()) {
                struct sockaddr_in* dst = peerAddr.load();
                if (dst) {
                    ssize_t sent = sendto(udpFd, buf, n, 0,
                                          (struct sockaddr*)dst, sizeof(*dst));
                    if (sent < 0 && errno != EAGAIN && errno != EWOULDBLOCK) {
                        std::cerr << "[TUN->UDP] sendto: " << strerror(errno) << std::endl;
                        s.err++;
                    } else if (sent > 0) { s.tx++; s.txB += sent; }
                }
            }
            lastHb = std::chrono::steady_clock::now();
        } else if (n < 0) { s.err++; break; }
        else {
            auto now = std::chrono::steady_clock::now();
            if (std::chrono::duration_cast<std::chrono::milliseconds>(now - lastHb).count() >= HB_INTERVAL_MS) {
                if (havePeer.load()) {
                    struct sockaddr_in* dst = peerAddr.load();
                    if (dst) {
                        uint8_t hb = HB_PING;
                        sendto(udpFd, &hb, 1, 0, (struct sockaddr*)dst, sizeof(*dst));
                        s.hb++;
                    }
                }
                lastHb = now;
            }
            usleep(5000);
        }
    }
}

/* ── UDP -> TUN ──────────────────────────────────────── */

static void udpToTun(TunIface& tun, int udpFd, Stats& s,
                   std::atomic<struct sockaddr_in*>& peerAddr,
                   std::atomic<bool>& havePeer) {
    uint8_t buf[MAX_IP_PACKET];
    struct sockaddr_in src = {};
    socklen_t srclen = sizeof(src);
    auto lastPkt = std::chrono::steady_clock::now();
    bool timedOutLogged = false;

    while (gRunning) {
        ssize_t n = recvfrom(udpFd, buf, sizeof(buf), 0,
                             (struct sockaddr*)&src, &srclen);
        if (n < 0) {
            if (errno == EAGAIN || errno == EWOULDBLOCK) {
                auto now = std::chrono::steady_clock::now();
                if (std::chrono::duration_cast<std::chrono::milliseconds>(now - lastPkt).count() > HB_TIMEOUT_MS) {
                    if (!timedOutLogged) {
                        std::cout << "[UDP->TUN] peer timeout, waiting..." << std::endl;
                        timedOutLogged = true;
                    }
                }
                usleep(10000);
                continue;
            }
            std::cerr << "[UDP->TUN] recvfrom: " << strerror(errno) << std::endl;
            s.err++; break;
        }

        lastPkt = std::chrono::steady_clock::now();
        timedOutLogged = false;

        // Learn peer address from first packet
        if (!havePeer.load()) {
            struct sockaddr_in* p = new struct sockaddr_in(src);
            struct sockaddr_in* old = peerAddr.exchange(p);
            delete old;
            havePeer.store(true);
            char ip[INET_ADDRSTRLEN];
            inet_ntop(AF_INET, &src.sin_addr, ip, sizeof(ip));
            std::cout << "[UDP->TUN] peer learned: " << ip << ":" << ntohs(src.sin_port) << std::endl;
        }

        if (n == 1) {
            if (buf[0] == HB_PING) {
                uint8_t pong = HB_PONG;
                sendto(udpFd, &pong, 1, 0, (struct sockaddr*)&src, sizeof(src));
            }
            s.hb++; continue;
        }

        if (n > 0 && n <= MAX_IP_PACKET) {
            int written = tun.writePacket(buf, n);
            if (written < 0) s.err++;
            else { s.rx++; s.rxB += written; }
        }
    }
}

/* ── main ────────────────────────────────────────────── */

int main(int argc, char* argv[]) {
    std::cout << "=== TUN_NAT_HUB UDP v3 ===" << std::endl;

    signal(SIGTERM, sigHandler);
    signal(SIGINT, sigHandler);
    signal(SIGPIPE, SIG_IGN);

    std::string tunName = "tun_hub";
    for (int i = 1; i < argc; i++) {
        std::string a = argv[i];
        if (a == "--tun" && i + 1 < argc) tunName = argv[++i];
    }

    try {
        TunIface tun(tunName);
        Stats stats;
        std::atomic<struct sockaddr_in*> peerAddr{nullptr};
        std::atomic<bool> havePeer{false};

        int udpFd = udpBind();
        if (udpFd < 0)
            throw std::runtime_error("UDP socket bind failed");

        std::thread t1(tunToUdp, std::ref(tun), udpFd, std::ref(stats),
                       std::ref(peerAddr), std::ref(havePeer));
        std::thread t2(udpToTun, std::ref(tun), udpFd, std::ref(stats),
                       std::ref(peerAddr), std::ref(havePeer));

        std::cout << "[main] IO threads started" << std::endl;

        while (gRunning) {
            sleep(1);
            static int tick = 0; tick++;
            if (tick % 5 == 0) {
                std::cout << "[stats] TX=" << stats.tx << "/" << stats.txB
                          << "B RX=" << stats.rx << "/" << stats.rxB
                          << "B HB=" << stats.hb << " err=" << stats.err << std::endl;
            }
        }

        std::cout << "[main] exiting..." << std::endl;
        tun.close();
        close(udpFd);
        t1.join(); t2.join();
    } catch (const std::exception& e) {
        std::cerr << "[FATAL] " << e.what() << std::endl;
        return 1;
    }
    return 0;
}
