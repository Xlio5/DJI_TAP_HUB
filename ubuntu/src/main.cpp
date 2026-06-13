/**
 * main.cpp — TUN_NAT_HUB ECM/RNDIS 模式 (UDP over usb0)
 *
 * 替换 g_serial TTY 模式，改用 ECM/RNDIS USB 网卡的 UDP socket。
 * 无需帧协议 — 原始 IP 包直接装入 UDP 数据报文。
 *
 * 主线程: 信号处理 + 统计输出
 * IO Thread 1: TUN.read() → sendto(Android, usb0:8899)
 * IO Thread 2: recvfrom(usb0:8899) → TUN.write()
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

// ── 常量 ──────────────────────────────────────────────

static constexpr int UDP_PORT         = 8899;
static constexpr int MAX_IP_PACKET    = 1500;   // 最大 IP 包 (含 IP 头)
static constexpr int HB_INTERVAL_MS   = 1000;   // 心跳间隔
static constexpr int HB_TIMEOUT_MS    = 5000;   // 对端超时
static constexpr uint8_t HB_PING      = 0x00;   // 心跳 ping 字节
static constexpr uint8_t HB_PONG      = 0x01;   // 心跳 pong 字节

// ── 统计 ──────────────────────────────────────────────

struct Stats {
    std::atomic<uint64_t> tx{0}, rx{0}, txB{0}, rxB{0}, err{0}, hb{0};
};

// ── UDP socket 工具 ───────────────────────────────────

/**
 * 创建绑定到指定接口地址的 UDP socket。
 * 非阻塞 + SO_REUSEADDR，绑定到 usb0 接口 IP。
 */
static int udpBind(const std::string& ifaceName) {
    int fd = socket(AF_INET, SOCK_DGRAM, 0);
    if (fd < 0) {
        std::cerr << "[UDP] socket 创建失败: " << strerror(errno) << std::endl;
        return -1;
    }

    // 非阻塞
    int flags = fcntl(fd, F_GETFL, 0);
    fcntl(fd, F_SETFL, flags | O_NONBLOCK);

    // 端口重用
    int reuse = 1;
    setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &reuse, sizeof(reuse));

    // 绑定到指定接口 (SO_BINDTODEVICE)
    struct ifreq ifr = {};
    strncpy(ifr.ifr_name, ifaceName.c_str(), IFNAMSIZ - 1);
    if (setsockopt(fd, SOL_SOCKET, SO_BINDTODEVICE, &ifr, sizeof(ifr)) < 0) {
        std::cerr << "[UDP] SO_BINDTODEVICE 失败: " << strerror(errno) << " (非致命)" << std::endl;
    }

    struct sockaddr_in addr = {};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(UDP_PORT);
    addr.sin_addr.s_addr = htonl(INADDR_ANY);  // 监听所有接口，配合 SO_BINDTODEVICE

    if (bind(fd, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
        std::cerr << "[UDP] bind 失败: " << strerror(errno) << std::endl;
        close(fd);
        return -1;
    }

    std::cout << "[UDP] socket 已绑定 " << ifaceName << ":" << UDP_PORT
              << " (fd=" << fd << ")" << std::endl;
    return fd;
}

// ── TUN → UDP ─────────────────────────────────────────

static void tunToUdp(TunIface& tun, int udpFd, Stats& s) {
    uint8_t buf[MAX_IP_PACKET];
    auto lastHb = std::chrono::steady_clock::now();

    // 目标地址 (首次 recvfrom 后更新)
    struct sockaddr_in dst = {};
    dst.sin_family = AF_INET;
    dst.sin_port = htons(UDP_PORT);
    dst.sin_addr.s_addr = inet_addr("10.0.0.255");  // 初始广播，收到包后更新
    bool havePeer = false;

    while (gRunning) {
        int n = tun.readPacket(buf, sizeof(buf));
        if (n > 0) {
            if (havePeer) {
                ssize_t sent = sendto(udpFd, buf, n, 0,
                                      (struct sockaddr*)&dst, sizeof(dst));
                if (sent < 0 && errno != EAGAIN && errno != EWOULDBLOCK) {
                    std::cerr << "[TUN→UDP] sendto 错误: " << strerror(errno) << std::endl;
                    s.err++;
                } else if (sent > 0) {
                    s.tx++;
                    s.txB += sent;
                }
            }
            // 无对端地址时丢弃（等待 Android 先发第一个包）
            lastHb = std::chrono::steady_clock::now();
        } else if (n < 0) {
            s.err++;
            break;
        } else {
            // n == 0, TUN 空读 (非阻塞无数据), 检查心跳
            auto now = std::chrono::steady_clock::now();
            if (std::chrono::duration_cast<std::chrono::milliseconds>(now - lastHb).count() >= HB_INTERVAL_MS) {
                if (havePeer) {
                    uint8_t hb = HB_PING;
                    sendto(udpFd, &hb, 1, 0, (struct sockaddr*)&dst, sizeof(dst));
                    s.hb++;
                }
                lastHb = now;
            }
            usleep(5000);
        }
    }
}

// ── UDP → TUN ─────────────────────────────────────────

static void udpToTun(TunIface& tun, int udpFd, Stats& s) {
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
                // 检查超时
                auto now = std::chrono::steady_clock::now();
                if (std::chrono::duration_cast<std::chrono::milliseconds>(now - lastPkt).count() > HB_TIMEOUT_MS) {
                    if (!timedOutLogged) {
                        std::cout << "[UDP→TUN] 对端超时，等待数据..." << std::endl;
                        timedOutLogged = true;
                    }
                }
                usleep(10000);
                continue;
            }
            std::cerr << "[UDP→TUN] recvfrom 错误: " << strerror(errno) << std::endl;
            s.err++;
            break;
        }

        lastPkt = std::chrono::steady_clock::now();
        timedOutLogged = false;

        // 心跳处理
        if (n == 1) {
            if (buf[0] == HB_PING) {
                // 收到 PING → 回复 PONG
                uint8_t pong = HB_PONG;
                sendto(udpFd, &pong, 1, 0, (struct sockaddr*)&src, sizeof(src));
            }
            // PONG 收到: 仅用于保活确认
            s.hb++;
            continue;
        }

        // 数据包: 写原始 IP 包到 TUN
        if (n > 0 && n <= MAX_IP_PACKET) {
            int written = tun.writePacket(buf, n);
            if (written < 0) s.err++;
            else { s.rx++; s.rxB += written; }
        }
    }
}

// ── 等待 usb0 就绪 ────────────────────────────────────

static int waitForUsb(std::string& ifaceName) {
    const char* candidates[] = {"usb0", "usb1", "rndis0", nullptr};
    for (int i = 0; i < 60 && gRunning; i++) {
        for (int j = 0; candidates[j] != nullptr; j++) {
            int fd = socket(AF_INET, SOCK_DGRAM, 0);
            if (fd < 0) continue;
            struct ifreq ifr = {};
            strncpy(ifr.ifr_name, candidates[j], IFNAMSIZ - 1);
            int ok = (ioctl(fd, SIOCGIFFLAGS, &ifr) == 0 && (ifr.ifr_flags & IFF_UP));
            close(fd);
            if (ok) {
                ifaceName = candidates[j];
                std::cout << "[等待] 接口 " << ifaceName << " 已就绪" << std::endl;
                return 0;
            }
        }
        if (i == 0) std::cerr << "[等待] 等待 USB Gadget 网络接口..." << std::endl;
        sleep(1);
    }
    return -1;
}

// ── main ──────────────────────────────────────────────

int main(int argc, char* argv[]) {
    std::cout << "=== TUN_NAT_HUB ECM/RNDIS v2 ===" << std::endl;

    signal(SIGTERM, sigHandler);
    signal(SIGINT, sigHandler);
    signal(SIGPIPE, SIG_IGN);

    std::string tunName = "tun_hub";
    std::string ifaceName = "usb0";
    for (int i = 1; i < argc; i++) {
        std::string a = argv[i];
        if (a == "--tun" && i + 1 < argc) tunName = argv[++i];
        else if (a == "--iface" && i + 1 < argc) ifaceName = argv[++i];
    }

    try {
        TunIface tun(tunName);
        Stats stats;

        // 等待 USB Gadget 接口就绪
        if (waitForUsb(ifaceName) < 0) {
            throw std::runtime_error("USB Gadget 接口 (" + ifaceName + ") 超时未就绪");
        }

        // 创建 UDP socket 并绑定到 ECM/RNDIS 接口
        int udpFd = udpBind(ifaceName);
        if (udpFd < 0) {
            throw std::runtime_error("无法绑定 UDP socket 到 " + ifaceName);
        }

        std::thread t1(tunToUdp, std::ref(tun), udpFd, std::ref(stats));
        std::thread t2(udpToTun, std::ref(tun), udpFd, std::ref(stats));

        std::cout << "[主] 双 IO 线程已启动" << std::endl;

        // 主循环: 统计输出
        while (gRunning) {
            sleep(1);
            static int tick = 0;
            tick++;

            if (tick % 5 == 0) {
                std::cout << "[统计] TX=" << stats.tx << "/" << stats.txB
                          << "B RX=" << stats.rx << "/" << stats.rxB
                          << "B HB=" << stats.hb << " err=" << stats.err << std::endl;
            }
        }

        std::cout << "[主] 正在退出..." << std::endl;
        tun.close();
        close(udpFd);
        t1.join();
        t2.join();
    } catch (const std::exception& e) {
        std::cerr << "[致命] " << e.what() << std::endl;
        return 1;
    }
    return 0;
}
