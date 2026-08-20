#include <cerrno>
#include <csignal>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>

#include <fcntl.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <termios.h>
#include <unistd.h>

#define termios asm_termios
#include <asm/termbits.h>
#undef termios

namespace {

volatile std::sig_atomic_t g_stop = 0;

void on_signal(int) {
    g_stop = 1;
}

class AuxTmuxRoute {
public:
    bool open_full_duplex() {
        const uintptr_t pio_phys = 0x01C20800u;
        const uintptr_t base = pio_phys & ~0xFFFu;
        const uintptr_t page_offset = pio_phys - base;
        page_size_ = static_cast<size_t>(::sysconf(_SC_PAGESIZE));

        int mem_fd = ::open("/dev/mem", O_RDWR | O_SYNC);
        if (mem_fd < 0) {
            std::fprintf(stderr, "aux_uart_test: open /dev/mem: %s\n", std::strerror(errno));
            return false;
        }
        map_ = ::mmap(nullptr, page_size_, PROT_READ | PROT_WRITE, MAP_SHARED,
                      mem_fd, static_cast<off_t>(base));
        ::close(mem_fd);
        if (map_ == MAP_FAILED) {
            map_ = nullptr;
            std::fprintf(stderr, "aux_uart_test: mmap PIO: %s\n", std::strerror(errno));
            return false;
        }

        auto *pio = static_cast<uint8_t *>(map_) + page_offset;
        cfg0_ = reinterpret_cast<volatile uint32_t *>(pio + 0x24);
        cfg1_ = reinterpret_cast<volatile uint32_t *>(pio + 0x28);
        data_ = reinterpret_cast<volatile uint32_t *>(pio + 0x34);
        old_cfg0_ = *cfg0_;
        old_cfg1_ = *cfg1_;
        old_data_ = *data_;

        uint32_t cfg0 = old_cfg0_;
        cfg0 = (cfg0 & ~(0xFu << 8)) | (0x1u << 8);
        cfg0 = (cfg0 & ~(0xFu << 12)) | (0x1u << 12);
        *cfg0_ = cfg0;

        uint32_t cfg1 = old_cfg1_;
        cfg1 = (cfg1 & ~(0xFu << 0)) | (0x1u << 0);
        cfg1 = (cfg1 & ~(0xFu << 4)) | (0x1u << 4);
        *cfg1_ = cfg1;

        uint32_t data = old_data_ & ~0x3Cu;
        data |= (1u << 2) | (1u << 3);  // NORMAL_RX_EN + TX_BUS_EN
        *data_ = data;
        ::usleep(10);

        std::printf("TMUX full-duplex: N=1 T=1 C=0 S=0 cfg0=0x%08x cfg1=0x%08x data=0x%08x\n",
                    *cfg0_, *cfg1_, *data_);
        return true;
    }

    ~AuxTmuxRoute() {
        if (map_ == nullptr) return;
        *data_ = old_data_;
        *cfg0_ = old_cfg0_;
        *cfg1_ = old_cfg1_;
        ::munmap(map_, page_size_);
        std::printf("TMUX registers restored\n");
    }

private:
    void *map_ = nullptr;
    size_t page_size_ = 0;
    volatile uint32_t *cfg0_ = nullptr;
    volatile uint32_t *cfg1_ = nullptr;
    volatile uint32_t *data_ = nullptr;
    uint32_t old_cfg0_ = 0;
    uint32_t old_cfg1_ = 0;
    uint32_t old_data_ = 0;
};

int open_uart(const char *device, int baud) {
    int fd = ::open(device, O_RDWR | O_NOCTTY);
    if (fd < 0) {
        std::fprintf(stderr, "aux_uart_test: open %s: %s\n", device, std::strerror(errno));
        return -1;
    }

    termios2 config{};
    if (::ioctl(fd, TCGETS2, &config) < 0) {
        std::fprintf(stderr, "aux_uart_test: TCGETS2 %s: %s\n", device, std::strerror(errno));
        ::close(fd);
        return -1;
    }
    config.c_iflag = IGNPAR;
    config.c_oflag = 0;
    config.c_lflag = 0;
    config.c_cflag = CLOCAL | CREAD | CS8;
    config.c_cflag &= ~(CBAUD | PARENB | PARODD | CSTOPB | CRTSCTS);
    config.c_cflag |= BOTHER | CS8;
    config.c_ispeed = static_cast<unsigned int>(baud);
    config.c_ospeed = static_cast<unsigned int>(baud);
    config.c_cc[VMIN] = 0;
    config.c_cc[VTIME] = 0;
    if (::ioctl(fd, TCSETS2, &config) < 0) {
        std::fprintf(stderr, "aux_uart_test: TCSETS2 %s: %s\n", device, std::strerror(errno));
        ::close(fd);
        return -1;
    }
    return fd;
}

bool send_message(int fd, const char *device, const char *name, unsigned int sequence) {
    char message[96];
    int length = std::snprintf(message, sizeof(message), "%s seq=%u\r\n", name, sequence);
    ssize_t written = ::write(fd, message, static_cast<size_t>(length));
    if (written == length && ::tcdrain(fd) == 0) {
        std::printf("%s wrote %d bytes: %s", device, length, message);
        return true;
    }
    std::fprintf(stderr, "%s write failed: expected=%d actual=%zd errno=%d(%s)\n",
                 device, length, written, errno, std::strerror(errno));
    return false;
}

}  // namespace

int main(int argc, char **argv) {
    int baud = 115200;
    unsigned int count = 60;
    unsigned int interval_ms = 1000;
    for (int i = 1; i < argc; ++i) {
        if (std::strcmp(argv[i], "--baud") == 0 && i + 1 < argc) {
            baud = std::atoi(argv[++i]);
        } else if (std::strcmp(argv[i], "--count") == 0 && i + 1 < argc) {
            count = static_cast<unsigned int>(std::strtoul(argv[++i], nullptr, 10));
        } else if (std::strcmp(argv[i], "--interval-ms") == 0 && i + 1 < argc) {
            interval_ms = static_cast<unsigned int>(std::strtoul(argv[++i], nullptr, 10));
        } else {
            std::fprintf(stderr, "usage: %s [--baud N] [--count N] [--interval-ms N]\n", argv[0]);
            return 2;
        }
    }
    if (baud <= 0 || count == 0 || interval_ms == 0) return 2;

    std::signal(SIGINT, on_signal);
    std::signal(SIGTERM, on_signal);

    AuxTmuxRoute route;
    if (!route.open_full_duplex()) return 1;

    int uart1 = open_uart("/dev/ttySC0", baud);
    int uart2 = open_uart("/dev/ttySC1", baud);
    if (uart1 < 0 || uart2 < 0) {
        if (uart1 >= 0) ::close(uart1);
        if (uart2 >= 0) ::close(uart2);
        return 1;
    }

    std::printf("AUX UART test started: baud=%d count=%u interval=%ums\n",
                baud, count, interval_ms);
    bool ok = true;
    for (unsigned int sequence = 1; sequence <= count && !g_stop; ++sequence) {
        ok = send_message(uart1, "/dev/ttySC0", "AUX-UART1", sequence) && ok;
        ok = send_message(uart2, "/dev/ttySC1", "AUX-UART2", sequence) && ok;
        ::usleep(interval_ms * 1000u);
    }

    ::close(uart1);
    ::close(uart2);
    return ok ? 0 : 1;
}
