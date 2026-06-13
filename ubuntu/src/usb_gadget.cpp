/**
 * usb_gadget.cpp — USB FunctionFS Gadget 实现
 *
 * FunctionFS (ffs) 工作原理：
 *   1. 用户态程序打开 /dev/usb-ffs/<name>/ep0
 *   2. 向 ep0 写入 USB 描述符（设备、配置、接口、端点）
 *   3. 向 ep0 写入空字符串（触发枚举完成）
 *   4. 内核创建 ep1 (Bulk OUT) 和 ep2 (Bulk IN)
 *   5. 用户态程序打开 ep1、ep2 进行数据收发
 *   6. 最后向 ep0 写入 "enable" 或设置 UDC 激活
 *
 * 参考: Linux 内核文档 Documentation/usb/functionfs.rst
 */

#include "usb_gadget.h"

#include <cstring>
#include <cerrno>
#include <stdexcept>
#include <iostream>
#include <fstream>
#include <vector>

#include <unistd.h>
#include <fcntl.h>
#include <sys/stat.h>
#include <dirent.h>

namespace tun_nat {

/* ── USB 描述符（硬编码，Vendor Specific Bulk 设备） ──────────── */

// 设备描述符 (18 bytes)
static const uint8_t DEVICE_DESC[] = {
    18,           // bLength
    0x01,         // bDescriptorType: Device
    0x00, 0x02,   // bcdUSB: 2.0
    0xFF,         // bDeviceClass: Vendor Specific
    0x00,         // bDeviceSubClass
    0x00,         // bDeviceProtocol
    64,           // bMaxPacketSize0
    0x07, 0x22,   // idVendor: 0x2207
    0x10, 0x00,   // idProduct: 0x0010
    0x00, 0x01,   // bcdDevice: 1.0
    0x01,         // iManufacturer
    0x02,         // iProduct
    0x03,         // iSerialNumber
    0x01          // bNumConfigurations
};

// 配置描述符 (9) + 接口描述符 (9) + 两个端点描述符 (7+7) = 32 bytes
static const uint8_t CONFIG_DESC[] = {
    // 配置描述符
    9,            // bLength
    0x02,         // bDescriptorType: Configuration
    32, 0x00,     // wTotalLength: 9+9+7+7 = 32
    0x01,         // bNumInterfaces
    0x01,         // bConfigurationValue
    0x00,         // iConfiguration
    0x80,         // bmAttributes: Bus Powered
    0xFA,         // bMaxPower: 500mA (0xFA * 2mA)

    // 接口描述符
    9,            // bLength
    0x04,         // bDescriptorType: Interface
    0x00,         // bInterfaceNumber
    0x00,         // bAlternateSetting
    0x02,         // bNumEndpoints: 2 (OUT + IN)
    0xFF,         // bInterfaceClass: Vendor Specific
    0x00,         // bInterfaceSubClass
    0x00,         // bInterfaceProtocol
    0x00,         // iInterface

    // 端点描述符: Bulk OUT (Host → Device)
    7,            // bLength
    0x05,         // bDescriptorType: Endpoint
    0x01,         // bEndpointAddress: EP1 OUT
    0x02,         // bmAttributes: Bulk
    0x00, 0x02,   // wMaxPacketSize: 512 (USB 2.0 HS)
    0x00,         // bInterval

    // 端点描述符: Bulk IN (Device → Host)
    7,            // bLength
    0x05,         // bDescriptorType: Endpoint
    0x82,         // bEndpointAddress: EP2 IN
    0x02,         // bmAttributes: Bulk
    0x00, 0x02,   // wMaxPacketSize: 512 (USB 2.0 HS)
    0x00,         // bInterval
};

/* ── 自动检测 UDC ──────────────────────────────────────────── */

static std::string detectUdc() {
    const std::string udcDir = "/sys/class/udc";
    DIR* dir = opendir(udcDir.c_str());
    if (!dir) {
        throw std::runtime_error("无法打开 " + udcDir + ": " + strerror(errno));
    }

    std::string result;
    struct dirent* entry;
    while ((entry = readdir(dir)) != nullptr) {
        if (entry->d_name[0] != '.') {
            result = entry->d_name;
            break;  // 取第一个
        }
    }
    closedir(dir);

    if (result.empty()) {
        throw std::runtime_error("未检测到可用的 UDC 控制器");
    }

    std::cout << "[USB] 自动检测 UDC: " << result << std::endl;
    return result;
}

/* ── UsbGadget 实现 ────────────────────────────────────────── */

UsbGadget::UsbGadget(const std::string& ffsPath, const std::string& udcName) {
    std::string ep0Path = ffsPath + "/ep0";

    // 打开 ep0
    ep0Fd_ = ::open(ep0Path.c_str(), O_RDWR);
    if (ep0Fd_ < 0) {
        throw std::runtime_error("无法打开 " + ep0Path + ": " + strerror(errno)
            + "\n请确认已执行 setup_gadget.sh");
    }

    // Step 1: 写入描述符
    writeDescriptors(ep0Fd_);

    // Step 2: 写入空字符串（触发端点创建）
    writeStrings(ep0Fd_);

    // Step 3: 内核创建了 ep1 和 ep2，打开它们
    std::string epOutPath = ffsPath + "/ep1";
    std::string epInPath  = ffsPath + "/ep2";

    epOutFd_ = ::open(epOutPath.c_str(), O_RDWR);
    if (epOutFd_ < 0) {
        int savedErr = errno;
        ::close(ep0Fd_);
        ep0Fd_ = -1;
        throw std::runtime_error("无法打开 " + epOutPath + ": " + strerror(savedErr));
    }

    epInFd_ = ::open(epInPath.c_str(), O_RDWR);
    if (epInFd_ < 0) {
        int savedErr = errno;
        ::close(epOutFd_);
        ::close(ep0Fd_);
        epOutFd_ = -1;
        ep0Fd_ = -1;
        throw std::runtime_error("无法打开 " + epInPath + ": " + strerror(savedErr));
    }

    std::cout << "[USB] FunctionFS 端点已打开: ep0=" << ep0Fd_
              << ", epOUT=" << epOutFd_ << ", epIN=" << epInFd_ << std::endl;

    // Step 4: 激活 UDC
    std::string udc = udcName.empty() ? detectUdc() : udcName;
    enableUdc(udc);

    ready_ = true;
    std::cout << "[USB] Gadget 已就绪，等待 Host 连接..." << std::endl;
}

UsbGadget::~UsbGadget() {
    close();
}

UsbGadget::UsbGadget(UsbGadget&& other) noexcept
    : ep0Fd_(other.ep0Fd_), epOutFd_(other.epOutFd_), epInFd_(other.epInFd_)
    , ready_(other.ready_)
{
    other.ep0Fd_ = -1;
    other.epOutFd_ = -1;
    other.epInFd_ = -1;
    other.ready_ = false;
}

UsbGadget& UsbGadget::operator=(UsbGadget&& other) noexcept {
    if (this != &other) {
        close();
        ep0Fd_ = other.ep0Fd_;
        epOutFd_ = other.epOutFd_;
        epInFd_ = other.epInFd_;
        ready_ = other.ready_;
        other.ep0Fd_ = -1;
        other.epOutFd_ = -1;
        other.epInFd_ = -1;
        other.ready_ = false;
    }
    return *this;
}

void UsbGadget::close() {
    if (epOutFd_ >= 0) { ::close(epOutFd_); epOutFd_ = -1; }
    if (epInFd_ >= 0)  { ::close(epInFd_);  epInFd_ = -1; }
    if (ep0Fd_ >= 0)   { ::close(ep0Fd_);   ep0Fd_ = -1; }
    ready_ = false;
    std::cout << "[USB] Gadget 已关闭" << std::endl;
}

void UsbGadget::writeDescriptors(int ep0Fd) {
    // FunctionFS V2 descriptor format (kernel 6.1):
    //
    // struct usb_functionfs_descs_head_v2 { __le32 magic; __le32 length; __le32 flags; };
    // Then manually appended fields based on flags:
    //   FUNCTIONFS_HAS_FS_DESC (1) → +4 bytes fs_count
    //   FUNCTIONFS_HAS_HS_DESC (2) → +4 bytes hs_count
    //   FUNCTIONFS_HAS_SS_DESC (4) → +4 bytes ss_count
    //   FUNCTIONFS_HAS_MS_OS_DESC (8) → +4 bytes os_count

    int descLen = sizeof(DEVICE_DESC) + sizeof(CONFIG_DESC);
    constexpr uint32_t kFlags = 1;  // FUNCTIONFS_HAS_FS_DESC
    constexpr uint32_t kFsCount = 2; // device + config

    // Header: 12 bytes (magic + length + flags) + 4 bytes (fs_count)
    constexpr int kHeaderLen = 16;
    int totalLen = kHeaderLen + descLen;

    std::vector<uint8_t> buf;
    buf.reserve(totalLen);

    auto pushLE32 = [&](uint32_t v) {
        buf.push_back(v & 0xFF);
        buf.push_back((v >> 8) & 0xFF);
        buf.push_back((v >> 16) & 0xFF);
        buf.push_back((v >> 24) & 0xFF);
    };

    pushLE32(3);        // magic = FUNCTIONFS_DESCRIPTORS_MAGIC_V2
    pushLE32(totalLen); // length
    pushLE32(kFlags);   // flags = FUNCTIONFS_HAS_FS_DESC
    pushLE32(kFsCount); // fs_count (appended manually per flags)

    buf.insert(buf.end(), DEVICE_DESC, DEVICE_DESC + sizeof(DEVICE_DESC));
    buf.insert(buf.end(), CONFIG_DESC, CONFIG_DESC + sizeof(CONFIG_DESC));

    ssize_t n = ::write(ep0Fd, buf.data(), buf.size());
    if (n != static_cast<ssize_t>(buf.size())) {
        throw std::runtime_error("写描述符失败: " + std::string(strerror(errno))
            + " (wrote " + std::to_string(n) + "/" + std::to_string(buf.size()) + ")");
    }

    std::cout << "[USB] FunctionFS V2 描述符已写入 (header=" << kHeaderLen
              << " + desc=" << descLen << " = " << totalLen << " bytes)" << std::endl;
}

void UsbGadget::writeStrings(int ep0Fd) {
    // FunctionFS: 写入空字符串触发枚举完成
    // 格式: 4 bytes zero length + empty data
    uint8_t zero[4] = {0, 0, 0, 0};
    if (::write(ep0Fd, zero, 4) != 4) {
        throw std::runtime_error("写 FunctionFS 字符串终止符失败: " + std::string(strerror(errno)));
    }
    std::cout << "[USB] FunctionFS 枚举触发完成" << std::endl;
}

void UsbGadget::enableUdc(const std::string& udcName) {
    std::string udcPath = "/sys/kernel/config/usb_gadget/tun_nat/UDC";
    std::ofstream udcFile(udcPath);
    if (!udcFile) {
        throw std::runtime_error("无法写入 UDC (" + udcPath + "): 请确认 setup_gadget.sh 已执行");
    }
    udcFile << udcName;
    udcFile.close();

    if (!udcFile) {
        throw std::runtime_error("写入 UDC 失败: " + udcName);
    }

    std::cout << "[USB] UDC 已激活: " << udcName << std::endl;
}

} // namespace tun_nat
