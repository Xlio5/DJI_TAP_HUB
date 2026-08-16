/**
 * tun_iface.cpp — TUN 虚拟网卡管理实现
 *
 * 使用 Linux /dev/net/tun 设备，IFF_TUN + IFF_NO_PI 模式。
 * IFF_NO_PI 表示内核不添加 4 字节的 packet info 前缀，
 * 读写的是纯净的 IP 包（与 Android VpnService TUN 行为一致）。
 */

#include "tun_iface.h"

#include <cstring>
#include <cerrno>
#include <stdexcept>
#include <sstream>
#include <iostream>

#include <unistd.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <sys/socket.h>
#include <netinet/in.h>
#include <arpa/inet.h>
#include <linux/if.h>
#include <linux/if_tun.h>

namespace tun_nat {

TunIface::TunIface(const std::string& name, int mtu)
    : name_(name), mtu_(mtu)
{
    fd_ = ::open("/dev/net/tun", O_RDWR);
    if (fd_ < 0) {
        throw std::runtime_error("无法打开 /dev/net/tun: " + std::string(strerror(errno)));
    }

    struct ifreq ifr = {};
    ifr.ifr_flags = IFF_TUN | IFF_NO_PI;   // L3 TUN，无 packet info 头
    strncpy(ifr.ifr_name, name_.c_str(), IFNAMSIZ - 1);

    if (ioctl(fd_, TUNSETIFF, &ifr) < 0) {
        int savedErr = errno;
        ::close(fd_);
        fd_ = -1;
        throw std::runtime_error("ioctl TUNSETIFF 失败: " + std::string(strerror(savedErr)));
    }

    // 设为非阻塞模式（配合心跳逻辑）
    int flags = fcntl(fd_, F_GETFL, 0);
    fcntl(fd_, F_SETFL, flags | O_NONBLOCK);

    // 实际名称可能被内核截断
    name_ = ifr.ifr_name;

    // 配置 tun 接口: MTU + UP + IP (自包含, 不依赖 setup_v3s.sh 时序)
    // 修复: usb_tund 重启后 tun_hub 可能 DOWN, 导致 write EIO, 隧道不转发
    configure(name_, mtu_);

    std::cout << "[TUN] 接口 '" << name_ << "' 已创建 (fd=" << fd_ << ", mtu=" << mtu_ << ")" << std::endl;
}

/// 配置 TUN 接口: 设置 MTU + UP (不配内部 IP, 手机地址由 setup_v3s.sh 用 /32 主机路由指向)
/// 2026-08-16: 砍掉 10.0.0.x 隧道网段 — tun_hub 不再配 10.0.0.1/24,
/// 只建 UP 接口, 避免生成 10.0.0.0/24 路由与 eth0 的 144.0/24 同网段冲突。
void TunIface::configure(const std::string& name, int mtu) {
    // 1. MTU
    int sock = ::socket(AF_INET, SOCK_DGRAM, 0);
    if (sock < 0) { std::cerr << "[TUN] socket 失败: " << strerror(errno) << std::endl; return; }
    struct ifreq ifr = {};
    strncpy(ifr.ifr_name, name.c_str(), IFNAMSIZ - 1);
    ifr.ifr_mtu = mtu;
    if (ioctl(sock, SIOCSIFMTU, &ifr) < 0)
        std::cerr << "[TUN] SIOCSIFMTU 失败: " << strerror(errno) << std::endl;

    // 2. UP
    if (ioctl(sock, SIOCGIFFLAGS, &ifr) < 0)
        std::cerr << "[TUN] SIOCGIFFLAGS 失败: " << strerror(errno) << std::endl;
    ifr.ifr_flags |= IFF_UP | IFF_RUNNING;
    if (ioctl(sock, SIOCSIFFLAGS, &ifr) < 0)
        std::cerr << "[TUN] SIOCSIFFLAGS(UP) 失败: " << strerror(errno) << std::endl;

    ::close(sock);
    std::cout << "[TUN] 配置 " << name << ": mtu=" << mtu << " UP (无内部 IP, 手机用 /32 路由)" << std::endl;
}

TunIface::~TunIface() {
    close();
}

TunIface::TunIface(TunIface&& other) noexcept
    : fd_(other.fd_), name_(std::move(other.name_)), mtu_(other.mtu_)
{
    other.fd_ = -1;
}

TunIface& TunIface::operator=(TunIface&& other) noexcept {
    if (this != &other) {
        close();
        fd_ = other.fd_;
        name_ = std::move(other.name_);
        mtu_ = other.mtu_;
        other.fd_ = -1;
    }
    return *this;
}

void TunIface::close() {
    if (fd_ >= 0) {
        std::cout << "[TUN] 关闭接口 '" << name_ << "' (fd=" << fd_ << ")" << std::endl;
        ::close(fd_);
        fd_ = -1;
    }
}

int TunIface::readPacket(uint8_t* buf, int maxLen) {
    ssize_t n = ::read(fd_, buf, maxLen);
    if (n < 0) {
        if (errno == EAGAIN || errno == EWOULDBLOCK) return 0;
        std::cerr << "[TUN] read 错误: " << strerror(errno) << std::endl;
        return -1;
    }
    return static_cast<int>(n);
}

int TunIface::writePacket(const uint8_t* data, int len) {
    ssize_t n = ::write(fd_, data, len);
    if (n < 0) {
        std::cerr << "[TUN] write 错误: " << strerror(errno) << std::endl;
        return -1;
    }
    return static_cast<int>(n);
}

} // namespace tun_nat
