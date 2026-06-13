/**
 * usb_gadget.h — USB FunctionFS Gadget 管理
 *
 * RK3588 端 USB Gadget (Device) 模式：
 * 使用 Linux ConfigFS + FunctionFS (ffs) 框架。
 *
 * 提供两个 Bulk 端点：
 *   - EP-OUT (host → device): Android → RK3588 方向
 *   - EP-IN  (device → host): RK3588 → Android 方向
 *
 * 使用流程：
 *   1. 先执行 setup_gadget.sh（创建 ConfigFS 目录结构 + 挂载 FunctionFS）
 *   2. 启动守护进程，调用 UsbGadget::init() 写入描述符并激活 UDC
 *   3. 通过 epOutFd() / epInFd() 读写
 */

#ifndef USB_TUND_USB_GADGET_H
#define USB_TUND_USB_GADGET_H

#include <cstdint>
#include <string>

namespace tun_nat {

/// USB Gadget 封装（RAII）
class UsbGadget {
public:
    /// 初始化 FunctionFS：写描述符，打开端点
    /// @param ffsPath  FunctionFS 挂载路径（如 "/dev/usb-ffs/tun_nat"）
    /// @param udcName  UDC 名称（如 "fc000000.usb"），空串表示自动检测
    explicit UsbGadget(const std::string& ffsPath, const std::string& udcName = "");

    ~UsbGadget();

    // 禁止拷贝
    UsbGadget(const UsbGadget&) = delete;
    UsbGadget& operator=(const UsbGadget&) = delete;

    // 允许移动
    UsbGadget(UsbGadget&& other) noexcept;
    UsbGadget& operator=(UsbGadget&& other) noexcept;

    /// Bulk-OUT 端点 fd（host→device，即 Android→RK3588）
    int epOutFd() const { return epOutFd_; }

    /// Bulk-IN 端点 fd（device→host，即 RK3588→Android）
    int epInFd() const { return epInFd_; }

    /// ep0 控制端点 fd（用于 descriptor 交互）
    int ep0Fd() const { return ep0Fd_; }

    /// 是否已初始化
    bool isReady() const { return ready_; }

    /// 关闭所有端点
    void close();

private:
    /// 写入 USB 描述符到 ep0（FunctionFS 协议要求）
    void writeDescriptors(int ep0Fd);

    /// 写入设备字符串到 ep0
    void writeStrings(int ep0Fd);

    /// 激活 UDC（使 Gadget 对 Host 可见）
    void enableUdc(const std::string& udcName);

    int ep0Fd_  = -1;   // 控制端点
    int epOutFd_ = -1;  // Bulk OUT
    int epInFd_  = -1;  // Bulk IN

    bool ready_ = false;
};

} // namespace tun_nat

#endif // USB_TUND_USB_GADGET_H
