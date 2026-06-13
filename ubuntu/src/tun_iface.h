/**
 * tun_iface.h — TUN 虚拟网卡管理
 *
 * 负责创建和配置 TUN 接口（/dev/net/tun），提供原始 IP 包读写。
 */

#ifndef USB_TUND_TUN_IFACE_H
#define USB_TUND_TUN_IFACE_H

#include <cstdint>
#include <string>

namespace tun_nat {

/// TUN 设备封装（RAII）
class TunIface {
public:
    /// 打开 TUN 设备
    /// @param name 接口名称（如 "tun_hub"）
    /// @param mtu  MTU 值（建议 1400）
    explicit TunIface(const std::string& name, int mtu = 1400);

    ~TunIface();

    // 禁止拷贝
    TunIface(const TunIface&) = delete;
    TunIface& operator=(const TunIface&) = delete;

    // 允许移动
    TunIface(TunIface&& other) noexcept;
    TunIface& operator=(TunIface&& other) noexcept;

    /// 获取文件描述符（用于 epoll / read / write）
    int fd() const { return fd_; }

    /// 接口名称
    const std::string& name() const { return name_; }

    /// MTU
    int mtu() const { return mtu_; }

    /// 从 TUN 读取一个原始 IP 包（阻塞）
    /// @return 读取的字节数；-1 表示错误
    int readPacket(uint8_t* buf, int maxLen);

    /// 写一个原始 IP 包到 TUN
    /// @return 写入的字节数；-1 表示错误
    int writePacket(const uint8_t* data, int len);

    /// 关闭 TUN 设备
    void close();

private:
    int fd_ = -1;
    std::string name_;
    int mtu_;
};

} // namespace tun_nat

#endif // USB_TUND_TUN_IFACE_H
