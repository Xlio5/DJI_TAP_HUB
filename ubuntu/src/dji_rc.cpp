/**
 * dji_rc.cpp — DJI DUML 双路串口解码守护进程 (V3s Linux)
 *
 * ttyS1 @921600 ← DJI-B (RC Plus 2 摇杆)
 * ttyS2 @115200 ← DJI-A (旧版遥控器按键)
 * 解码 → 融合 → SBUS输出(ttyS2 TX) → 状态文件(/var/log/rc_state.json)
 *
 * web_server 的 /api/rc 直接读 /var/log/rc_state.json
 *
 * 编译: arm-buildroot-linux-gnueabihf-g++ -std=c++17 -O2 -s -lpthread
 */
#include <atomic>
#include <cerrno>
#include <cstdio>
#include <cstdarg>
#include <cstdlib>
#include <cstring>
#include <ctime>
#include <mutex>
#include <string>
#include <thread>

#include <arpa/inet.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/socket.h>
#include <termios.h>
#include <unistd.h>

extern "C" {
#include "duml.h"
#include "rc_decode.h"
#include "chmap.h"
#include "sbus.h"
#include "crsf.h"
#include "rc_map.h"
}

// 自定义波特率 (termios2 BOTHER): 标准 termios 表没有 100000/400000/420000。
// 用宏把内核 <asm/termbits.h> 的 struct termios 重命名, 避免与 glibc <termios.h> 冲突。
#define termios asm_termios
#include <asm/termbits.h>
#undef termios

// ═══════════════════════════════════════════════════════════════════════
// 端口状态
// ═══════════════════════════════════════════════════════════════════════

struct DjiPort {
    const char *tag;
    int         fd;
    rc_state_t  state;
    uint32_t    good     = 0;
    uint32_t    other    = 0;
    uint32_t    rx_bytes = 0;
    int64_t     last_us  = 0;
    uint8_t     dbg_b[16];
};

// ═══════════════════════════════════════════════════════════════════════
// 共享融合态 (主线程 + 两个rx线程都访问)
// ═══════════════════════════════════════════════════════════════════════

static DjiPort g_p20;      // ttyS1 @921600
static DjiPort g_p0;       // ttyS2 @115200
static std::mutex g_mtx;
static std::atomic<bool> g_stop{false};
static std::atomic<bool> g_crsf_stop{false};   /* 独立控制 CRSF 回传线程 (t3), 不干扰 t1/t2 */
static int g_debug_fd = -1;
static int64_t g_last_debug_us = 0;

// ── 输出 (SBUS/CRSF @UART0) ──
// C1: g_out_fd 被多线程 (rx_thread/t3/主线程) 无锁访问, 用 atomic 避免 fd 值撕裂
static std::atomic<int> g_out_fd{-1};
static std::atomic<char> g_out_mode{'s'}; // 's' = SBUS, 'c' = CRSF
static std::atomic<int>  g_out_baud{100000}; // 实际波特率 (SBUS标准=100000, SBUS非标=115200, CRSF=420000)
static std::mutex g_out_write_mtx;        // CO-4: 保护对 g_out_fd 的写 (out_send + crsf_rx_thread 并发)
static bool g_sbus_std = true;          // SBUS 标准模式: true=100k 8E2, false=115200 8N1
static bool g_crsf_telem = true;        // CRSF 是否接收回传
static std::atomic<bool> g_ch_map_valid{false};  // CRIT#2: atomic, 主线程热重配写 + rx_thread 读
static uint8_t g_ch_map[CH_COUNT];      // 通道映射表 (读写受 g_mtx 保护)
static crsf_telem_t g_telem;            // 最近回传数据 (CRSF 回传线程写)
static bool g_pb6_debug = false;        // PB6 接地=true → UART0 作为 debug 串口, 不输出协议

// ── CRSF 参数表 (供 Device_Ping/Parameter_Read 响应, ELRS 协议) ──
static crsf_param_t g_crsf_params[] = {
    /* id, parent, type, flags, min, max, def, unit, name */
    { 0, 0xFF, CRSF_PTYPE_FOLDER, 0, {0},{0},{0}, "", "V3s Hub" },
    { 1, 0, CRSF_PTYPE_TEXT_SEL, 0, {0},{2},{0}, "", "Output Mode" },
    { 2, 0, CRSF_PTYPE_UINT32, 0,
      {0,0,0,0}, {0,0,0x0F,0xA0}, {0,0,1,0x86}, "bps", "Baudrate" },
    { 3, 0, CRSF_PTYPE_UINT8, 0, {0},{100},{50}, "%", "Telemetry" },
};
static uint8_t g_crsf_n_params = (uint8_t)(sizeof(g_crsf_params) / sizeof(g_crsf_params[0]));

/* 参数表运行时初始化: 设默认值 + 文本选项 (C++ 无法在静态初始化里用 strncpy) */
static void crsf_params_init(void)
{
    for (uint8_t i = 0; i < g_crsf_n_params; i++) {
        uint8_t w = 1;
        switch (g_crsf_params[i].type & 0x7F) {
        case CRSF_PTYPE_UINT16: case CRSF_PTYPE_INT16: w = 2; break;
        case CRSF_PTYPE_UINT32: case CRSF_PTYPE_INT32: case CRSF_PTYPE_FLOAT: w = 4; break;
        default: break;
        }
        memcpy(g_crsf_params[i].value, g_crsf_params[i].def, w);
        g_crsf_params[i].value_len = w;
    }
    /* 文本选项 */
    memset(g_crsf_params[1].text_opts, 0, sizeof(g_crsf_params[1].text_opts));
    strncpy((char *)g_crsf_params[1].text_opts[0], "SBUS", 16);
    strncpy((char *)g_crsf_params[1].text_opts[1], "CRSF", 16);
    strncpy((char *)g_crsf_params[1].text_opts[2], "Auto", 16);
    g_crsf_params[1].n_opts = 3;
}

// PB6 输入检测: 接地(0) → debug 模式; 上拉(1,默认) → 协议输出
// 用 mmap /dev/mem 读物理寄存器。每次检测重新 open+mmap+munmap (新虚拟地址映射同一物理页),
// 避免同一次映射读到旧值 (运行中切换失效的根因假设)。
// sun8i-v3s GPIO: pinctrl base @0x01C20800, bank 内存 0x24 (BANK_MEM_SIZE)。
// PB = bank 1 → bank offset 0x24。PB bank 寄存器:
//   CFG0 (PB0-3) @0x24, CFG1 (PB4-7) @0x28, PB6 = CFG1 bit 24-25 (值 0=input)
//   DATA (PB0-31) @0x34, PB6 = bit6
//   PU0 (PB0-15)  @0x40, PB6 = bit 12-13 (值 01=pull-up)
// 失败时返回 false (协议输出) 保持默认安全。
static bool pb6_grounded(void)
{
    /* 注意: 0x01C20800 & ~0xFFF = 0x01C20000 是 clock 区!
     * 必须加页内偏移 0x800 才能访问到 pinctrl (0x01C20800)。 */
    const uintptr_t PIO_PHYS  = 0x01C20800u;      /* pinctrl 物理基址 */
    const uintptr_t BASE      = PIO_PHYS & ~0xFFFu;  /* 页对齐 0x01C20000 */
    const uintptr_t PAGE_OFF  = PIO_PHYS - BASE;      /* 0x800, 页内偏移 */
    const size_t    PG        = (size_t)sysconf(_SC_PAGESIZE);

    // 注: 此函数需要 O_RDWR (154-162 行配置 PB6 为 input + pull-up), 功能必需。
    // 风险缓解: 每次 open+mmap+munmap+close, 写窗口极短。
    int memfd = ::open("/dev/mem", O_RDWR | O_SYNC);
    if (memfd < 0) {
        std::fprintf(stderr, "[dji_rc] PB6 检测: 无法打开 /dev/mem (%s)\n", std::strerror(errno));
        return false;
    }
    void *map = mmap(NULL, PG, PROT_READ | PROT_WRITE, MAP_SHARED, memfd, (off_t)BASE);
    ::close(memfd);
    if (map == MAP_FAILED) {
        std::fprintf(stderr, "[dji_rc] PB6 检测: mmap 失败 (%s)\n", std::strerror(errno));
        return false;
    }

    uint8_t *pio = (uint8_t *)map + PAGE_OFF;    /* 指向 0x01C20800 */
    volatile uint32_t *cfg1 = (volatile uint32_t *)(pio + 0x28);  /* PB CFG1 (PB4-7) */
    volatile uint32_t *data = (volatile uint32_t *)(pio + 0x34);  /* PB DATA */
    volatile uint32_t *pu0  = (volatile uint32_t *)(pio + 0x40);  /* PB PU0 */

    /* 1. 强制 PB6 为 input (CFG1 bit24-25 = 00) */
    uint32_t c = *cfg1;
    c &= ~(0x3u << 24);
    *cfg1 = c;
    /* 2. 强制 PB6 pull-up (PU0 bit12-13 = 01) */
    uint32_t pu = *pu0;
    pu &= ~(0x3u << 12);
    pu |= (0x1u << 12);
    *pu0 = pu;
    /* 3. 短延时等寄存器生效 */
    ::usleep(1000);
    /* 4. 读 DATA bit6: 0=接地, 1=上拉 */
    uint32_t reg = *data;
    bool grounded = ((reg >> 6) & 1u) == 0;

    /* 诊断打印 (仅首次调用, 避免每次 poll 刷屏) */
    static bool dbg_once = false;
    if (!dbg_once) {
        dbg_once = true;
        std::printf("[dji_rc] PB6 检测: CFG1=0x%08X PU0=0x%08X DATA=0x%08X grounded=%d\n",
                    (unsigned)c, (unsigned)pu, (unsigned)reg, grounded ? 1 : 0);
        std::fflush(stdout);
    }

    munmap(map, PG);
    return grounded;
}

/* 启动/停止 ttyS0 getty (debug 串口登录终端) */
static void getty_start(void)
{
    /* 先确保无残留 getty (busybox 无 pkill, 用 killall), 再启动新的 */
    ::system("killall getty 2>/dev/null");
    ::usleep(100000);   /* 等旧 getty 完全退出释放 ttyS0 */
    if (::system("setsid /sbin/getty -L 115200 ttyS0 vt100 >/dev/null 2>&1 &") != 0) {
        std::fprintf(stderr, "[dji_rc] getty 启动命令失败\n");
    }
}

static void getty_stop(void)
{
    /* 杀掉所有挂 ttyS0 的进程 (含 getty + login shell):
     * - killall getty 只杀 getty 进程, 但 getty 派生出的 login shell (-sh) 不是 getty,
     *   killall 杀不到, 会一直占用 ttyS0, 导致切回协议时 uart_open_out 失败。
     * - fuser -k /dev/ttyS0 按终端杀所有占用进程 (busybox 内置 fuser)。
     * - inittab 若仍有 ttyS0::respawn:/sbin/getty, 杀掉的 getty 会被立刻 respawn,
     *   需在 rootfs 构建时禁用该行 (见 build_rootfs_v*.sh)。 */
    ::system("killall getty 2>/dev/null");
    ::system("fuser -k /dev/ttyS0 2>/dev/null");
    ::usleep(300000);   /* 等进程完全退出并释放 ttyS0 (避免 fd 占用) */
}

static int uart_open_out(const char *dev, int baud, bool even2);   /* forward */
static void crsf_rx_thread();                                       /* forward */

// ── PB6 运行中自动切换 (每 2s 检测, 连续 N 次相同才切换, 防抖) ──
// 主循环调用。接地→debug(启 getty + 关协议), 上拉→协议(杀 getty + 开协议)。
// 需要访问 main 局部变量 (out_dev/out_mode/out_baud/t3), 由 main 传入。
static void pb6_auto_switch(bool grounded, const char *out_dev, char out_mode,
                            int out_baud, bool &out_pb6_debug, std::thread &t3)
{
    static int same_count = 0;
    static bool last = false;
    const int NEED = 3;   /* 连续 3 次相同才切换 (6s 确认) */

    if (grounded == last) {
        same_count++;
    } else {
        same_count = 1;
        last = grounded;
    }
    if (same_count < NEED) return;
    if (grounded == out_pb6_debug) return;   /* 状态未变, 已确认 */

    same_count = 0;
    std::printf("[dji_rc] PB6 变化 → %s\n", grounded ? "debug 模式" : "协议模式");
    std::fflush(stdout);

    if (grounded) {
        /* 切到 debug: 停协议输出 + 启 getty */
        if (t3.joinable()) {
            g_crsf_stop.store(true);
            int oldFd = g_out_fd.exchange(-1);   // C1: atomic 取出并置 -1
            if (oldFd >= 0) { ::close(oldFd); }
            t3.join();
            g_crsf_stop.store(false);
        }
        int oldFd2 = g_out_fd.exchange(-1);      // C1: atomic
        if (oldFd2 >= 0) { ::close(oldFd2); }
        getty_start();
        out_pb6_debug = true;
    } else {
        /* 切到协议: 杀 getty + 开协议输出 (等 getty 释放 ttyS0) */
        getty_stop();
        ::usleep(200000);   /* 200ms, 等 getty 释放 ttyS0 */
        if (g_out_fd.load() < 0) {
            bool even2 = (g_out_mode.load() == 's') && g_sbus_std;   /* 用全局, 避免参数过期 */
            g_out_fd.store(uart_open_out(out_dev, g_out_baud.load(), even2));   // 复审: 用 atomic g_out_baud, 避免过时参数
        }
        if (g_out_mode.load() == 'c' && g_crsf_telem && g_out_fd.load() >= 0 && !t3.joinable()) {
            g_crsf_stop.store(false);
            t3 = std::thread(crsf_rx_thread);
        }
        out_pb6_debug = false;
    }
    (void)out_mode;   /* 已改用全局 g_out_mode */
}

// ── rcmsg (RC 数据 UDP) ──
static constexpr uint32_t RCMSG_MAGIC = 0x314D4352u;  // "RCM1", little-endian on wire
static constexpr int RCMSG_PORT = 65530;
static constexpr const char *RCMSG_HOST = "10.0.0.2";

// ── CRSF 桥 (crsf-bridge 模式): UART0 CRSF 帧 ↔ 网口 UDP 透明转发 ──
// App 跑 ELRS Lua 脚本, 经网口 UDP 发 CRSF 参数命令, V3s 转 UART0。
static bool g_crsf_bridge = false;   // --crsf-bridge 启用
static constexpr uint32_t CRSFBR_MAGIC = 0x46534352u;   // "RCSF" little-endian = "CRSF"
static int       crsfbr_port = 65532;                   // 网口 CRSF 桥端口
static const char *crsfbr_host = "10.0.0.2";

// ── tlm (回传数据 UDP) ──
static constexpr uint32_t TLM_MAGIC = 0x314D4C54u;    // "TLM1", little-endian on wire
static constexpr int TLM_PORT = 65531;
static int g_tlm_fd = -1;

#pragma pack(push, 1)
struct RcMsg {
    uint32_t magic;
    uint16_t version;
    uint16_t size;
    uint32_t seq;
    uint64_t ts_us;
    uint16_t ch[CH_COUNT];
    int16_t raw_ch[6];
    uint32_t buttons;
    uint8_t mode;
    uint8_t dial;
    uint16_t flags;
};
#pragma pack(pop)

static void debug_log(const char *fmt, ...);

// ═══════════════════════════════════════════════════════════════════════
// helpers
// ═══════════════════════════════════════════════════════════════════════

static int64_t now_us() {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    // CRIT#1: 用 1000000LL, 避免 32-bit ARM 上 ts.tv_sec*1000000 (long) 35分钟溢出回卷
    return (int64_t)ts.tv_sec * 1000000LL + ts.tv_nsec / 1000;
}

static void debug_uart0_open(const char *dev, int baud)
{
    g_debug_fd = ::open(dev, O_WRONLY | O_NOCTTY | O_NONBLOCK);
    if (g_debug_fd < 0) {
        std::fprintf(stderr, "[dji_rc] debug uart open %s failed: %s\n",
                     dev, std::strerror(errno));
        return;
    }

    struct termios tty;
    std::memset(&tty, 0, sizeof(tty));
    if (tcgetattr(g_debug_fd, &tty) == 0) {
        tty.c_iflag = IGNPAR;
        tty.c_oflag = 0;
        tty.c_cflag = CLOCAL | CREAD | CS8;
        tty.c_lflag = 0;
        tty.c_cc[VMIN] = 0;
        tty.c_cc[VTIME] = 0;
        speed_t spd = (baud == 921600) ? B921600 : B115200;
        cfsetispeed(&tty, spd);
        cfsetospeed(&tty, spd);
        tcsetattr(g_debug_fd, TCSANOW, &tty);
    }

    debug_log("[dji_rc][dbg] uart0 debug enabled dev=%s baud=%d", dev, baud);
}

static void debug_log(const char *fmt, ...)
{
    if (g_debug_fd < 0) return;

    char buf[256];
    va_list ap;
    va_start(ap, fmt);
    int n = std::vsnprintf(buf, sizeof(buf), fmt, ap);
    va_end(ap);
    if (n <= 0) return;
    if (n > (int)sizeof(buf) - 3) n = sizeof(buf) - 3;
    buf[n++] = '\r';
    buf[n++] = '\n';
    ::write(g_debug_fd, buf, n);
}

static int uart_open(const char *dev, int baud)
{
    int fd = ::open(dev, O_RDWR | O_NOCTTY);  // blocking: VMIN/VTIME handles timeout
    if (fd < 0) {
        std::fprintf(stderr, "[dji_rc] 无法打开 %s: %s\n", dev, std::strerror(errno));
        return -1;
    }

    struct termios tty;
    std::memset(&tty, 0, sizeof(tty));
    tcgetattr(fd, &tty);

    // 输入: 忽略parity/framing错误, 不映射CR, 不流控
    tty.c_iflag = IGNPAR;
    tty.c_oflag = 0;
    tty.c_cflag = CLOCAL | CREAD | CS8;
    tty.c_lflag = 0;          // raw mode

    // VMIN=1 (至少读1字节), VTIME=1 (100ms超时)
    tty.c_cc[VMIN]  = 1;
    tty.c_cc[VTIME] = 1;

    speed_t spd;
    switch (baud) {
        case 115200: spd = B115200; break;
        case 921600: spd = B921600; break;
        default:     spd = B115200; break;
    }
    cfsetispeed(&tty, spd);
    cfsetospeed(&tty, spd);

    tcflush(fd, TCIOFLUSH);
    tcsetattr(fd, TCSANOW, &tty);

    std::printf("[dji_rc] %s @%d 已打开 fd=%d\n", dev, baud, fd);
    return fd;
}

/* 打开 UART0 作为协议输出口 (SBUS/CRSF), 支持任意波特率 + 8E2/8N1。
 * even2: true=偶校验+2停止位(SBUS 100k 8E2), false=8N1(CRSF)。
 * 波特率用 termios2 BOTHER 设任意值(100000/420000 等非标准)。
 */
static int uart_open_out(const char *dev, int baud, bool even2)
{
    int fd = ::open(dev, O_RDWR | O_NOCTTY | O_NONBLOCK);
    if (fd < 0) {
        std::fprintf(stderr, "[dji_rc] 输出口打开失败 %s: %s\n", dev, std::strerror(errno));
        return -1;
    }

    struct termios2 t2;
    std::memset(&t2, 0, sizeof(t2));
    if (ioctl(fd, TCGETS2, &t2) < 0) {
        std::fprintf(stderr, "[dji_rc] TCGETS2 失败 %s: %s\n", dev, std::strerror(errno));
        ::close(fd);
        return -1;
    }
    t2.c_iflag = IGNPAR;
    t2.c_oflag = 0;
    t2.c_lflag = 0;
    t2.c_cflag = CLOCAL | CREAD | CS8;
    t2.c_cflag &= ~(CBAUD | PARENB | PARODD | CSTOPB | CRTSCTS);
    t2.c_cflag |= BOTHER | CS8;
    if (even2) t2.c_cflag |= PARENB | CSTOPB;   /* 8E2: 偶校验 + 2 停止位 */
    t2.c_ispeed = baud;
    t2.c_ospeed = baud;
    t2.c_cc[VMIN]  = 0;
    t2.c_cc[VTIME] = 0;
    if (ioctl(fd, TCSETS2, &t2) < 0) {
        std::fprintf(stderr, "[dji_rc] TCSETS2 失败 %s @%d: %s\n", dev, baud, std::strerror(errno));
        ::close(fd);
        return -1;
    }

    std::printf("[dji_rc] 输出 %s @%d %s fd=%d\n", dev, baud, even2 ? "8E2" : "8N1", fd);
    debug_log("[dji_rc][dbg] out %s @%d %s fd=%d", dev, baud, even2 ? "8E2" : "8N1", fd);
    return fd;
}

static int rcmsg_open(const char *host, int port, sockaddr_in *dst)
{
    int fd = ::socket(AF_INET, SOCK_DGRAM, 0);
    if (fd < 0) {
        std::fprintf(stderr, "[dji_rc] rcmsg socket failed: %s\n", std::strerror(errno));
        return -1;
    }

    std::memset(dst, 0, sizeof(*dst));
    dst->sin_family = AF_INET;
    dst->sin_port = htons((uint16_t)port);
    if (::inet_aton(host, &dst->sin_addr) == 0) {
        std::fprintf(stderr, "[dji_rc] rcmsg bad host: %s\n", host);
        ::close(fd);
        return -1;
    }

    /* 非阻塞: 目标不可达时 sendto 立即返回 EAGAIN, 避免 UDP 发送缓冲区
     * 填满后阻塞主循环 (曾卡在 sock_alloc_send_pskb, 导致主循环停 + PB6 poll 失效)。 */
    int fl = ::fcntl(fd, F_GETFL, 0);
    if (fl >= 0) ::fcntl(fd, F_SETFL, fl | O_NONBLOCK);

    std::printf("[dji_rc] rcmsg UDP: %s:%d fd=%d\n", host, port, fd);
    debug_log("[dji_rc][dbg] rcmsg UDP %s:%d fd=%d", host, port, fd);
    return fd;
}

static uint32_t button_bits(const rc_state_t &st)
{
    uint32_t b = 0;
    if (st.btn)      b |= 1u << 0;
    if (st.stop)     b |= 1u << 1;
    if (st.focus)    b |= 1u << 2;
    if (st.shot)     b |= 1u << 3;
    if (st.rec)      b |= 1u << 4;
    if (st.rth)      b |= 1u << 5;
    if (st.c1)       b |= 1u << 6;
    if (st.c2)       b |= 1u << 7;
    if (st.c3)       b |= 1u << 8;
    if (st.up)       b |= 1u << 9;
    if (st.down)     b |= 1u << 10;
    if (st.left)     b |= 1u << 11;
    if (st.right)    b |= 1u << 12;
    if (st.aircraft) b |= 1u << 13;
    if (st.back)     b |= 1u << 14;
    return b;
}

static void send_rcmsg(int fd, const sockaddr_in &dst, const rc_state_t &st,
                       bool valid, uint32_t seq, int64_t ts_us)
{
    if (fd < 0) return;

    RcMsg msg{};
    msg.magic = RCMSG_MAGIC;
    msg.version = 1;
    msg.size = sizeof(RcMsg);
    msg.seq = seq;
    msg.ts_us = (uint64_t)ts_us;
    msg.mode = (uint8_t)(valid ? st.mode : '?');
    msg.dial = valid ? st.dial : 0;
    msg.flags = valid ? 1u : 0u;

    rc_state_t neutral{};
    neutral.mode = '?';
    const rc_state_t &src = valid ? st : neutral;
    chmap_build(&src, msg.ch);
    for (int i = 0; i < 6; i++) msg.raw_ch[i] = src.ch[i];
    msg.buttons = valid ? button_bits(st) : 0;

    ssize_t n = ::sendto(fd, &msg, sizeof(msg), MSG_DONTWAIT,
                         (const sockaddr *)&dst, sizeof(dst));
    if (n != (ssize_t)sizeof(msg)) {
        /* 目标不可达/缓冲区满时 sendto 返回 EAGAIN, 忽略 (主循环不能阻塞) */
        if (errno != EAGAIN && errno != EWOULDBLOCK)
            std::fprintf(stderr, "[dji_rc] rcmsg send fail n=%d errno=%d\n", (int)n, errno);
    }
}

// ── 处理一个DUML包 → 更新端口状态 ──────────────────────────────

static void sbus_send_if_p20(DjiPort *p);  // forward: 定义在 SBUS 输出区域

static void handle_pkt(DjiPort *p, const duml_pkt_t *pk)
{
    rc_state_t st;
    bool ok = false;

    if (pk->cmd_set == 6 && pk->cmd_id == 0xAE)
        ok = decode_rc_ae(pk->payload, pk->payload_len, &st);
    else if (pk->cmd_set == 1 && pk->cmd_id == 0x02)
        ok = decode_special_02(pk->payload, pk->payload_len, &st);

    int64_t ts = now_us();

    if (ok) {
        p->state  = st;
        p->good++;
        p->last_us = ts;
    } else {
        p->other++;
    }
    int nb = pk->payload_len < 16 ? pk->payload_len : 16;
    for (int i = 0; i < nb; i++) p->dbg_b[i] = pk->payload[i];
}

// ── 串口接收线程 ──────────────────────────────────────────────

static void rx_thread(DjiPort *p)
{
    uint8_t buf[2048];
    int len = 0;

    while (!g_stop.load(std::memory_order_relaxed)) {
        int n = ::read(p->fd, buf + len, sizeof(buf) - len);
        if (n > 0) {
            len += n;
            g_mtx.lock();
            p->rx_bytes += n;
            g_mtx.unlock();
        } else if (n < 0 && errno != EAGAIN && errno != EINTR) {
            std::fprintf(stderr, "[dji_rc] %s read error: %s\n", p->tag, std::strerror(errno));
            break;  // exit thread on hardware error
        }

        int off = 0;
        while (len - off >= 1) {
            duml_pkt_t pk;
            int r = duml_parse(buf + off, len - off, &pk);
            if (r < 0) break;
            if (r == 0) { off += 1; continue; }

            g_mtx.lock();
            handle_pkt(p, &pk);
            g_mtx.unlock();
            sbus_send_if_p20(p);  // SBUS write outside mutex: no blocking I/O in critical section
            off += pk.pkt_len;
        }

        if (off > 0) {
            std::memmove(buf, buf + off, len - off);
            len -= off;
        }
        // 安全阀
        if (len == (int)sizeof(buf)) {
            std::memmove(buf, buf + 1, len - 1);
            len -= 1;
        }
    }
}

// ── 自检 ──────────────────────────────────────────────────────

static bool selftest()
{
    static const uint8_t sample[] = {
        0x55,0x1A,0x04,0xB1,0x06,0x0E,0x5C,0x95,0x00,0x01,0x02,
        0x00,0x00,0x04,0x20,0x00,0x01,0x08,0x40,0x00,0x02,0x00,0x00,0x0A,0xAD,0x26
    };

    std::printf("[dji_rc] selftest: DUML parsing...\n");
    duml_pkt_t pk;
    int r = duml_parse(sample, (int)sizeof(sample), &pk);
    if (r <= 0) {
        std::fprintf(stderr, "[dji_rc] selftest FAIL: duml_parse=%d\n", r);
        return false;
    }
    std::printf("[dji_rc]   duml OK: len=%d cmd_set=%d cmd_id=0x%02X\n",
                pk.pkt_len, pk.cmd_set, pk.cmd_id);

    if (!(pk.cmd_set == 1 && pk.cmd_id == 0x02)) {
        std::fprintf(stderr, "[dji_rc] selftest FAIL: not SPECIAL/0x02\n");
        return false;
    }

    rc_state_t st;
    if (!decode_special_02(pk.payload, pk.payload_len, &st)) {
        std::fprintf(stderr, "[dji_rc] selftest FAIL: decode_special_02\n");
        return false;
    }
    std::printf("[dji_rc]   decode: %s ch1=%+d ch6=%+d mode=%c\n",
                rc_type_name(st.type), st.ch[0], st.ch[5], st.mode);

    // RC/0xAE decode
    uint8_t pl_ae[17] = {};
    pl_ae[2] = 0x04;  // mode=N (01)
    for (int i = 0; i < 6; i++) {
        pl_ae[5 + i*2] = (1024 + 100*(i-2)) & 0xFF;
        pl_ae[6 + i*2] = ((1024 + 100*(i-2)) >> 8) & 0xFF;
    }
    rc_state_t st2;
    if (!decode_rc_ae(pl_ae, 17, &st2)) {
        std::fprintf(stderr, "[dji_rc] selftest FAIL: decode_rc_ae\n");
        return false;
    }
    std::printf("[dji_rc]   RC/0xAE: ch1=%+d ch6=%+d mode=%c\n",
                st2.ch[0], st2.ch[5], st2.mode);

    // channel mapping
    uint16_t ch[16];
    chmap_build(&st2, ch);
    std::printf("[dji_rc]   chmap: ch1=%u ch7=%u ch14=%u ch16=%u\n",
                ch[0], ch[6], ch[13], ch[15]);

    // SBUS
    uint8_t frame[25];
    sbus_encode(ch, frame);
    bool sbus_ok = (frame[0] == 0x0F && frame[24] == 0x00);
    std::printf("[dji_rc]   SBUS: frame[0]=0x%02X frame[24]=0x%02X %s\n",
                frame[0], frame[24], sbus_ok ? "OK" : "FAIL");

    // rc_merge
    rc_state_t m;
    rc_merge(&st2, 10000, &st, 5000, 500000000, &m);
    std::printf("[dji_rc]   merge: type=%s ch1=%+d mode=%c\n",
                rc_type_name(m.type), m.ch[0], m.mode);

    std::printf("[dji_rc] selftest PASSED\n\n");
    return true;
}

// ── 写状态文件(std::string, 无fmt库依赖) ──────────────────────

static void write_state_file(const rc_state_t &st, uint32_t g1, uint32_t g2,
                             uint32_t rx1, uint32_t rx2, int64_t ts_us)
{
    uint16_t ch[CH_COUNT];
    chmap_build(&st, ch);

    char buf[2048];
    int w = snprintf(buf, sizeof(buf),
        "{\"ch1\":%u,\"ch2\":%u,\"ch3\":%u,\"ch4\":%u,\"ch5\":%u,\"ch6\":%u,"
        "\"ch7\":%u,\"ch8\":%u,\"ch9\":%u,\"ch10\":%u,\"ch11\":%u,\"ch12\":%u,"
        "\"ch13\":%u,\"ch14\":%u,\"ch15\":%u,\"ch16\":%u,"
        "\"raw_ch1\":%d,\"raw_ch2\":%d,\"raw_ch3\":%d,\"raw_ch4\":%d,"
        "\"raw_ch5\":%d,\"raw_ch6\":%d,"
        "\"mode\":\"%c\",\"btn\":%d,\"stop\":%d,\"focus\":%d,\"shot\":%d,\"rec\":%d,"
        "\"rth\":%d,\"c1\":%d,\"c2\":%d,\"c3\":%d,\"dial\":%d,"
        "\"up\":%d,\"down\":%d,\"left\":%d,\"right\":%d,\"aircraft\":%d,\"back\":%d,"
        "\"good1\":%u,\"good2\":%u,\"rx1\":%u,\"rx2\":%u,"
        "\"type\":\"%s\",\"ts_us\":%lld}\n",
        ch[0], ch[1], ch[2], ch[3], ch[4], ch[5], ch[6], ch[7],
        ch[8], ch[9], ch[10], ch[11], ch[12], ch[13], ch[14], ch[15],
        st.ch[0], st.ch[1], st.ch[2], st.ch[3], st.ch[4], st.ch[5],
        st.mode, st.btn, st.stop, st.focus, st.shot, st.rec,
        st.rth, st.c1, st.c2, st.c3, st.dial,
        st.up, st.down, st.left, st.right, st.aircraft, st.back,
        g1, g2, rx1, rx2, rc_type_name(st.type),
        (long long)ts_us);

    // atomic write: tmp → rename
    // H: snprintf 返回值可能超过 sizeof(buf) 或为负, clamp 避免越界写
    if (w < 0) w = 0;                       // 复审: 负值(编码错误) → 0
    if (w > (int)sizeof(buf)) w = (int)sizeof(buf);
    int fd = ::open("/var/log/rc_state.json.tmp", O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fd >= 0) {
        ssize_t written = ::write(fd, buf, w);
        ::close(fd);
        if (written == w)
            ::rename("/var/log/rc_state.json.tmp", "/var/log/rc_state.json");
        else
            std::fprintf(stderr, "[dji_rc] state write: wrote %zd of %d\n", written, w);
    }
}

// ── 协议输出: P20 每解一帧就立刻发 (SBUS/CRSF 由 g_out_mode 决定) ──────

static void out_send(const rc_state_t &m)
{
    static uint32_t out_attempts = 0;
    static uint32_t out_errors = 0;
    int outFd = g_out_fd.load();            // C1: atomic load
    char outMode = g_out_mode.load();       // C1: atomic load
    if (outFd < 0) return;

    uint16_t ch[CH_COUNT];
    // C-1: 持锁拷贝 g_ch_map, 避免与主线程热重配 (load_rc_output_cfg) 的数据竞争。
    // g_ch_map_valid 只作为"映射是否有效"标志, 拷贝必须在 g_mtx 内完成,
    // 否则 reader 可能在 writer 写入过程中读到 torn map (g_ch_map_valid 永不复位的场景)。
    uint8_t mapSnap[CH_COUNT];
    bool mapValid = false;
    {
        std::lock_guard<std::mutex> lock(g_mtx);
        mapValid = g_ch_map_valid.load(std::memory_order_acquire);
        if (mapValid) std::memcpy(mapSnap, g_ch_map, CH_COUNT);
    }
    rc_map_build(&m, mapValid ? mapSnap : NULL, ch);

    int n = 0;
    if (outMode == 'c') {
        uint8_t frame[CRSF_FRAME_MAX];
        n = crsf_pack_channels(ch, frame);
        if (n > 0) {
            std::lock_guard<std::mutex> lock(g_out_write_mtx);   // CO-4: 串口写互斥, 防 CRSF 帧交错
            if (g_out_fd.load() != outFd) return;                // CO-5: fd 已被替换, 丢弃本次输出
            ssize_t w = ::write(outFd, frame, (size_t)n);
            out_attempts++;
            if (w != n) { out_errors++; }
        }
    } else {
        uint8_t frame[SBUS_FRAME_LEN];
        sbus_encode(ch, frame);
        std::lock_guard<std::mutex> lock(g_out_write_mtx);       // CO-4: 串口写互斥
        if (g_out_fd.load() != outFd) return;                    // CO-5: fd 已被替换
        ssize_t w = ::write(outFd, frame, SBUS_FRAME_LEN);
        out_attempts++;
        if (w != SBUS_FRAME_LEN) { out_errors++; }
    }

    if (out_errors && out_attempts <= 10) {
        std::printf("[dji_rc] out write fail attempts=%u errors=%u errno=%d\n",
                    out_attempts, out_errors, errno);
        debug_log("[dji_rc][dbg] out write fail attempts=%u errors=%u errno=%d",
                  out_attempts, out_errors, errno);
    } else if ((out_attempts <= 10 || (out_attempts % 100) == 0) && out_errors == 0) {
        std::printf("[dji_rc] out ok mode=%c attempts=%u ch1=%u ch2=%u ch3=%u ch4=%u\n",
                    outMode, out_attempts, ch[0], ch[1], ch[2], ch[3]);
        debug_log("[dji_rc][dbg] out ok mode=%c attempts=%u ch1=%u ch2=%u ch3=%u ch4=%u",
                  outMode, out_attempts, ch[0], ch[1], ch[2], ch[3]);
    }
}

/* P20 解到帧时的事件驱动发送 (forward 声明在 rx_thread 上方) */
static void sbus_send_if_p20(DjiPort *p)
{
    if (p != &g_p20) return;
    if (g_out_fd.load() < 0) return;   // C1: atomic load

    int64_t n = now_us();

    // CO-2/CO-3: 持锁拷贝 state, 避免与 P0 rx_thread / 主线程热重配的数据竞争
    rc_state_t s20, s0;
    int64_t l20, l0;
    g_mtx.lock();
    s20 = g_p20.state; l20 = g_p20.last_us;
    s0  = g_p0.state;  l0  = g_p0.last_us;
    g_mtx.unlock();

    if (s20.type == RC_NONE) return;
    if ((n - l20) > 500000LL) return;

    int64_t age20 = n - l20;
    int64_t age0  = (s0.type == RC_NONE) ? INT64_MAX : n - l0;

    rc_state_t m;
    rc_merge(&s20, age20, &s0, age0, 500000LL, &m);

    if (m.type != RC_NONE) out_send(m);   // write() outside mutex
}

// ── CRSF 回传接收线程: 读 UART0 上行帧 (GPS/BATT/ATT/VARIO/LINK) ──

static void crsf_rx_thread()
{
    crsf_rx_t rx;
    crsf_rx_init(&rx);

    /* 设备描述 (Device_Info 响应用, 非 bridge 模式) */
    static crsf_dev_desc_t dev;
    memset(&dev, 0, sizeof(dev));
    strncpy(dev.name, "V3s-Hub", sizeof(dev.name) - 1);
    dev.serial_hi = 0x01; dev.serial_lo = 0x46;   /* v1.4.x */
    dev.hw_ver = 0x01; dev.sw_ver = 0x01;
    dev.proto_ver = 2;                             /* ELRS 参数协议 v2 */

    /* bridge 模式: 参数帧转发网口 UDP */
    int crsfbr_fd = -1;
    sockaddr_in crsfbr_dst;
    if (g_crsf_bridge) {
        crsfbr_fd = rcmsg_open(crsfbr_host, crsfbr_port, &crsfbr_dst);
    }

    while (!g_crsf_stop.load(std::memory_order_relaxed)) {
        int outFd = g_out_fd.load();   // C1: atomic load
        if (outFd < 0) { ::usleep(10000); continue; }
        uint8_t buf[64];
        ssize_t n = ::read(outFd, buf, sizeof(buf));
        if (n > 0) {
            crsf_telem_t telem = g_telem;
            for (ssize_t i = 0; i < n; i++) {
                int r = crsf_rx_byte(&rx, buf[i]);
                if (r > 0) {
                    uint8_t type = rx.buf[2];
                    if (crsf_parse_frame(rx.buf, (uint8_t)r, &telem))
                        telem.last_rx_us = now_us();
                    if (g_crsf_bridge) {
                        /* bridge 模式: 参数帧(0x28+) 原样转发网口 UDP */
                        if (type >= 0x28 && crsfbr_fd >= 0) {
                            uint8_t pkt[4 + CRSF_FRAME_MAX];
                            uint32_t m = CRSFBR_MAGIC;
                            memcpy(pkt, &m, 4);
                            memcpy(pkt + 4, rx.buf, (size_t)r);
                            ssize_t w = ::sendto(crsfbr_fd, pkt, 4 + (size_t)r, MSG_DONTWAIT,
                                                 (const sockaddr *)&crsfbr_dst, sizeof(crsfbr_dst));
                            (void)w;
                        }
                    } else {
                        /* 设备/参数请求 → 生成响应写回 UART0 上行 */
                        if (type >= 0x28) {
                            uint8_t resp[CRSF_FRAME_MAX];
                            int rlen = crsf_handle_request(rx.buf, (uint8_t)r, &dev,
                                                           g_crsf_params, g_crsf_n_params, resp);
                            if (rlen > 0) {
                                std::lock_guard<std::mutex> lock(g_out_write_mtx);  // CO-4: 串口写互斥, 防与下行帧交错
                                if (g_out_fd.load() != outFd) continue;             // CO-5: fd 已替换
                                ssize_t w = ::write(outFd, resp, (size_t)rlen);
                                (void)w;
                            }
                        }
                    }
                        /* 设备/参数请求 → 生成响应写回 UART0 上行 */
                        if (type >= 0x28) {
                            uint8_t resp[CRSF_FRAME_MAX];
                            int rlen = crsf_handle_request(rx.buf, (uint8_t)r, &dev,
                                                           g_crsf_params, g_crsf_n_params, resp);
                            if (rlen > 0) {
                                ssize_t w = ::write(g_out_fd, resp, (size_t)rlen);
                                (void)w;
                            }
                        }
                    }
                }
            }
            g_mtx.lock();
            g_telem = telem;
            g_mtx.unlock();
        } else if (n < 0 && errno != EAGAIN && errno != EINTR) {
            if (g_crsf_stop.load(std::memory_order_relaxed)) break;
            ::usleep(20000);   /* 硬件错误, 短暂等待后重试 */
        } else {
            ::usleep(2000);    /* 无数据, 2ms 轮询 (O_NONBLOCK) */
        }
    }
    if (crsfbr_fd >= 0) ::close(crsfbr_fd);
}

/* ── bridge 下行线程: 收网口 UDP CRSF 命令 → 写 UART0 ── */
static void crsf_bridge_rx_thread()
{
    int fd = ::socket(AF_INET, SOCK_DGRAM, 0);
    if (fd < 0) return;
    int fl = ::fcntl(fd, F_GETFL, 0);
    if (fl >= 0) ::fcntl(fd, F_SETFL, fl | O_NONBLOCK);
    int yes = 1;
    ::setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &yes, sizeof(yes));

    sockaddr_in sa;
    std::memset(&sa, 0, sizeof(sa));
    sa.sin_family = AF_INET;
    sa.sin_addr.s_addr = htonl(INADDR_ANY);
    sa.sin_port = htons((uint16_t)crsfbr_port);
    if (::bind(fd, (sockaddr *)&sa, sizeof(sa)) < 0) {
        std::fprintf(stderr, "[dji_rc] crsf-bridge bind 失败: %s\n", std::strerror(errno));
        ::close(fd);
        return;
    }

    std::printf("[dji_rc] crsf-bridge 监听 UDP %s:%d → UART0\n", crsfbr_host, crsfbr_port);

    while (!g_crsf_stop.load(std::memory_order_relaxed)) {
        uint8_t pkt[4 + CRSF_FRAME_MAX];
        ssize_t n = ::recvfrom(fd, pkt, sizeof(pkt), 0, NULL, NULL);
        if (n > 0) {
            /* 校验 magic "CRSF" + 帧长合法, 原样写 UART0 */
            if (n >= 5 && memcmp(pkt, &CRSFBR_MAGIC, 4) == 0) {
                uint8_t flen = pkt[4 + 1];   /* CRSF len 字段 */
                if (flen + 2 == (uint8_t)(n - 4) && g_out_fd >= 0) {
                    ::write(g_out_fd, pkt + 4, (size_t)(n - 4));
                }
            }
        } else if (n < 0 && errno != EAGAIN && errno != EINTR) {
            if (g_crsf_stop.load(std::memory_order_relaxed)) break;
            ::usleep(20000);
        } else {
            ::usleep(2000);
        }
    }
    ::close(fd);
}

// ── 回传数据 UDP 发送 (TLM1) ──────────────────────────────────────

#pragma pack(push, 1)
struct TlmMsg {
    uint32_t magic;
    uint16_t version;
    uint16_t size;
    uint64_t ts_us;
    int8_t   up_rssi1, up_rssi2, up_snr;
    uint8_t  up_quality;
    int8_t   dn_rssi1, dn_rssi2, dn_snr;
    uint8_t  dn_quality;
    uint8_t  has_gps;
    int32_t  lat_degE7, lon_degE7;
    uint16_t gps_speed_kmh10, gps_heading_deg10;
    int32_t  gps_alt_mm;
    uint8_t  gps_sats;
    uint8_t  has_batt;
    uint16_t batt_voltage_mV10, batt_current_mA10;
    uint32_t batt_capacity_mAh;
    uint8_t  batt_remaining_pct;
    uint8_t  has_att;
    int16_t  att_pitch_deg100, att_roll_deg100, att_yaw_deg100;
    uint8_t  has_vario;
    int32_t  vario_cms;
    uint8_t  has_fmode;
    char     flight_mode[24];
};
#pragma pack(pop)

static void send_tlm(int fd, const sockaddr_in &dst, const crsf_telem_t &t)
{
    if (fd < 0) return;
    TlmMsg msg{};
    msg.magic = TLM_MAGIC;
    msg.version = 1;
    msg.size = sizeof(TlmMsg);
    msg.ts_us = (uint64_t)t.last_rx_us;
    msg.up_rssi1 = t.up_rssi1; msg.up_rssi2 = t.up_rssi2; msg.up_snr = t.up_snr;
    msg.up_quality = t.up_quality;
    msg.dn_rssi1 = t.dn_rssi1; msg.dn_rssi2 = t.dn_rssi2; msg.dn_snr = t.dn_snr;
    msg.dn_quality = t.dn_quality;
    msg.has_gps = t.has_gps; msg.lat_degE7 = t.lat_degE7; msg.lon_degE7 = t.lon_degE7;
    msg.gps_speed_kmh10 = t.gps_speed_kmh10; msg.gps_heading_deg10 = t.gps_heading_deg10;
    msg.gps_alt_mm = t.gps_alt_mm; msg.gps_sats = t.gps_sats;
    msg.has_batt = t.has_batt; msg.batt_voltage_mV10 = t.batt_voltage_mV10;
    msg.batt_current_mA10 = t.batt_current_mA10; msg.batt_capacity_mAh = t.batt_capacity_mAh;
    msg.batt_remaining_pct = t.batt_remaining_pct;
    msg.has_att = t.has_att; msg.att_pitch_deg100 = t.att_pitch_deg100;
    msg.att_roll_deg100 = t.att_roll_deg100; msg.att_yaw_deg100 = t.att_yaw_deg100;
    msg.has_vario = t.has_vario; msg.vario_cms = t.vario_cms;
    msg.has_fmode = t.has_fmode; memcpy(msg.flight_mode, t.flight_mode, sizeof(msg.flight_mode));

    ::sendto(fd, &msg, sizeof(msg), MSG_DONTWAIT, (const sockaddr *)&dst, sizeof(dst));
}

/* 回传数据写状态文件 (供 web_server /api/rc/telemetry) */
static void write_telem_file(const crsf_telem_t &t)
{
    char buf[512];
    int w = snprintf(buf, sizeof(buf),
        "{\"ts_us\":%lld,\"link\":{\"up_rssi\":%d,\"up_snr\":%d,\"up_quality\":%d,"
        "\"dn_rssi\":%d,\"dn_snr\":%d,\"dn_quality\":%d},"
        "\"gps\":{\"has\":%d,\"lat\":%lld,\"lon\":%lld,\"speed_kmh10\":%u,"
        "\"heading_deg10\":%u,\"alt_mm\":%lld,\"sats\":%u},"
        "\"batt\":{\"has\":%d,\"voltage_mv10\":%u,\"current_ma10\":%u,"
        "\"capacity_mah\":%u,\"remaining_pct\":%u},"
        "\"att\":{\"has\":%d,\"pitch_deg100\":%d,\"roll_deg100\":%d,\"yaw_deg100\":%d},"
        "\"vario_cms\":%lld,\"flight_mode\":\"%s\"}\n",
        (long long)t.last_rx_us, t.up_rssi1, t.up_snr, t.up_quality,
        t.dn_rssi1, t.dn_snr, t.dn_quality,
        t.has_gps ? 1 : 0, (long long)t.lat_degE7, (long long)t.lon_degE7,
        t.gps_speed_kmh10, t.gps_heading_deg10, (long long)t.gps_alt_mm, t.gps_sats,
        t.has_batt ? 1 : 0, t.batt_voltage_mV10, t.batt_current_mA10,
        t.batt_capacity_mAh, t.batt_remaining_pct,
        t.has_att ? 1 : 0, t.att_pitch_deg100, t.att_roll_deg100, t.att_yaw_deg100,
        (long long)t.vario_cms, t.flight_mode);
    // H: snprintf 返回值可能超过 sizeof(buf) 或为负, clamp 避免越界写
    if (w < 0) w = 0;                       // 复审: 负值(编码错误) → 0
    if (w > (int)sizeof(buf)) w = (int)sizeof(buf);
    int fd = ::open("/var/log/rc_telem.json.tmp", O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fd >= 0) {
        if (::write(fd, buf, w) == w)
            ::rename("/var/log/rc_telem.json.tmp", "/var/log/rc_telem.json");
        ::close(fd);
    }
}

// ═══════════════════════════════════════════════════════════════════════
// 输出配置 (从 SPI flash config 读取, 与 web_server 共用存储)
// ═══════════════════════════════════════════════════════════════════════

static std::string cfg_json_str(const std::string &json, const std::string &key) {
    auto pos = json.find("\"" + key + "\"");
    if (pos == std::string::npos) return "";
    auto colon = json.find(":", pos + key.size() + 2);
    if (colon == std::string::npos) return "";
    size_t s = colon + 1;
    while (s < json.size() && (json[s] == ' ' || json[s] == '\t' || json[s] == '\n')) s++;
    if (s < json.size() && json[s] == '\"') {
        auto e = json.find("\"", s + 1);
        if (e == std::string::npos) return "";
        return json.substr(s + 1, e - s - 1);
    }
    auto e = json.find_first_of(",}\n\r \t]", s + 1);
    if (e == std::string::npos) e = json.size();
    auto v = json.substr(s, e - s);
    while (!v.empty() && v.back() == ' ') v.pop_back();
    return v;
}

/* 从 SPI flash config (/dev/mtdblock0 @0xFD000) 读 rc_output 配置。
 * 返回 false 表示无 rc_output 段 (保持命令行默认)。成功则写 mode/baud/sbus_std 并
 * 可能更新 g_ch_map / g_ch_map_valid。 */
static bool load_rc_output_cfg(char &mode, int &baud, bool &sbus_std)
{
    bool found = false;
    int fd = ::open("/dev/mtdblock0", O_RDONLY);
    if (fd < 0) return false;
    uint16_t len = 0;
    ::lseek(fd, 0xFD000, SEEK_SET);
    if (::read(fd, &len, 2) != 2 || len == 0 || len > 0x3000) { ::close(fd); return false; }
    std::string json((size_t)len, '\0');
    ssize_t got = ::read(fd, &json[0], len);
    ::close(fd);
    if (got != (ssize_t)len) return false;

    auto rp = json.find("\"rc_output\"");
    if (rp == std::string::npos) return false;
    auto rs = json.find("{", rp);
    auto re = json.find("}", rs);
    if (rs == std::string::npos || re == std::string::npos) return false;
    std::string obj = json.substr(rs, re - rs + 1);

    auto modeS = cfg_json_str(obj, "mode");
    if (modeS == "crsf") { mode = 'c'; found = true; }
    else if (modeS == "sbus") { mode = 's'; found = true; }

    auto stdS = cfg_json_str(obj, "sbus_std");
    if (stdS == "false") sbus_std = false;
    else if (stdS == "true") sbus_std = true;

    auto baudS = cfg_json_str(obj, "baud");
    /* 标准 SBUS: 100k 8E2; 非标准: 115200 8N1; CRSF: 420k 8N1 */
    if (baudS == "auto" || baudS.empty()) {
        if (mode == 'c') baud = 420000;
        else if (sbus_std) baud = 100000;
        else baud = 115200;
    } else { int b = std::atoi(baudS.c_str()); if (b >= 9600 && b <= 4000000) baud = b; }

    auto presetS = cfg_json_str(obj, "map_preset");
    auto preset = rc_preset_parse(presetS.c_str());
    // C-1: 写 g_ch_map 前先复位 valid, 让 out_send 的读者跳过旧映射, 再在锁内更新。
    // 解析失败 (map 为空/项数不足) 时保持 invalid, 避免使用上一轮的旧映射。
    g_mtx.lock();
    g_ch_map_valid.store(false, std::memory_order_release);
    if (preset != MAP_CUSTOM) {
        rc_map_apply_preset(preset, g_ch_map);
        g_ch_map_valid.store(true, std::memory_order_release);
    } else {
        /* map: 逗号分隔 source 名, 如 "ch1,ch2,ch3,ch4,ch5,ch6,mode,rec,..." */
        std::string mapS = cfg_json_str(obj, "map");
        if (!mapS.empty()) {
            int idx = 0; size_t pos = 0;
            while (idx < CH_COUNT) {
                auto comma = mapS.find(",", pos);
                std::string tok = mapS.substr(pos, comma == std::string::npos ? std::string::npos : comma - pos);
                while (!tok.empty() && (tok.front() == ' ' || tok.front() == '\t')) tok.erase(0, 1);
                while (!tok.empty() && (tok.back() == ' ' || tok.back() == '\t')) tok.pop_back();
                if (!tok.empty()) g_ch_map[idx] = (uint8_t)rc_src_parse(tok.c_str());
                idx++;
                if (comma == std::string::npos) break;
                pos = comma + 1;
            }
            if (idx >= CH_COUNT) g_ch_map_valid.store(true, std::memory_order_release);
        }
    }
    g_mtx.unlock();
    return found;
}

// ═══════════════════════════════════════════════════════════════════════
// main
// ═══════════════════════════════════════════════════════════════════════

int main(int argc, char **argv)
{
    const char *dev1 = "/dev/ttyS1";
    const char *dev2 = "/dev/ttyS2";
    int baud1 = 921600;
    int baud2 = 115200;
    int interval_ms = 100;
    bool debug_uart0 = false;
    const char *debug_dev = "/dev/ttyS0";
    int debug_baud = 115200;
    const char *out_dev = "/dev/ttyS0";      /* 协议输出口: 默认 UART0 */
    char out_mode = 's';                     /* 's'=SBUS, 'c'=CRSF */
    int  out_baud = 100000;                  /* 默认 SBUS 100k */
    bool crsf_telem = true;                  /* CRSF 接收回传 */
    const char *rcmsg_host = RCMSG_HOST;
    int rcmsg_port = RCMSG_PORT;

    // 简易参数解析
    for (int i = 1; i < argc; i++) {
        if (std::strcmp(argv[i], "--ttyS1") == 0 && i + 1 < argc) dev1 = argv[++i];
        else if (std::strcmp(argv[i], "--ttyS2") == 0 && i + 1 < argc) dev2 = argv[++i];
        else if (std::strcmp(argv[i], "--baud1") == 0 && i + 1 < argc) baud1 = std::atoi(argv[++i]);
        else if (std::strcmp(argv[i], "--baud2") == 0 && i + 1 < argc) baud2 = std::atoi(argv[++i]);
        else if (std::strcmp(argv[i], "--interval") == 0 && i + 1 < argc) interval_ms = std::atoi(argv[++i]);
        else if (std::strcmp(argv[i], "--debug-uart0") == 0) debug_uart0 = true;
        else if (std::strcmp(argv[i], "--debug-uart0-dev") == 0 && i + 1 < argc) debug_dev = argv[++i];
        else if (std::strcmp(argv[i], "--debug-uart0-baud") == 0 && i + 1 < argc) debug_baud = std::atoi(argv[++i]);
        else if (std::strcmp(argv[i], "--out-mode") == 0 && i + 1 < argc) out_mode = argv[++i][0];
        else if (std::strcmp(argv[i], "--out-dev") == 0 && i + 1 < argc) out_dev = argv[++i];
        else if (std::strcmp(argv[i], "--out-baud") == 0 && i + 1 < argc) out_baud = std::atoi(argv[++i]);
        else if (std::strcmp(argv[i], "--crsf-telem") == 0 && i + 1 < argc) crsf_telem = std::atoi(argv[++i]) != 0;
        else if (std::strcmp(argv[i], "--sbus-out") == 0 && i + 1 < argc) { out_dev = argv[++i]; out_mode = 's'; }
        else if (std::strcmp(argv[i], "--sbus-baud") == 0 && i + 1 < argc) out_baud = std::atoi(argv[++i]);
        else if (std::strcmp(argv[i], "--rcmsg-host") == 0 && i + 1 < argc) rcmsg_host = argv[++i];
        else if (std::strcmp(argv[i], "--rcmsg-port") == 0 && i + 1 < argc) rcmsg_port = std::atoi(argv[++i]);
        else if (std::strcmp(argv[i], "--crsf-bridge") == 0) g_crsf_bridge = true;
        else if (std::strcmp(argv[i], "--crsfbr-host") == 0 && i + 1 < argc) crsfbr_host = argv[++i];
        else if (std::strcmp(argv[i], "--crsfbr-port") == 0 && i + 1 < argc) { crsfbr_port = std::atoi(argv[++i]); }
        else if (std::strcmp(argv[i], "--selftest") == 0) { selftest(); return 0; }
    }

    // 输出配置: SPI flash config 优先 (web_server 保存的 rc_output)
    char cfg_mode = out_mode; int cfg_baud = out_baud; bool cfg_std = g_sbus_std;
    if (load_rc_output_cfg(cfg_mode, cfg_baud, cfg_std)) {
        out_mode = cfg_mode; out_baud = cfg_baud; g_sbus_std = cfg_std;
        std::printf("[dji_rc] 输出配置(SPI flash): mode=%c baud=%d sbus_std=%d\n",
                    out_mode, out_baud, g_sbus_std ? 1 : 0);
    }
    g_out_mode.store(out_mode);   // C1: atomic store
    if (out_baud == 0) out_baud = (out_mode == 'c') ? 420000 : (g_sbus_std ? 100000 : 115200);
    g_out_baud.store(out_baud);   /* 先修复零值再赋值 */  // C1: atomic store
    g_crsf_telem = crsf_telem;

    /* bridge 模式: 强制 CRSF 输出 (UART0 双向 CRSF, 参数帧透明转发) */
    if (g_crsf_bridge) {
        out_mode = 'c';
        g_out_mode = 'c';
        g_crsf_telem = true;
        if (out_baud == 0) out_baud = 420000;
        g_out_baud = out_baud;
        std::printf("[dji_rc] crsf-bridge 模式: UART0 CRSF %d baud, 参数帧转发网口\n", out_baud);
    }

    if (debug_uart0) debug_uart0_open(debug_dev, debug_baud);

    std::printf("\n=== DJI RC daemon (V3s) ===\n");
    std::printf("P20: %s @%d  |  P0: %s @%d  |  print every %dms\n\n",
                dev1, baud1, dev2, baud2, interval_ms);

    if (!selftest()) return 1;

    // 初始化端口
    g_p20.tag = "P20"; g_p0.tag = "P0";
    g_p20.fd = uart_open(dev1, baud1);
    g_p0.fd  = uart_open(dev2, baud2);
    if (g_p20.fd < 0 && g_p0.fd < 0) {
        std::fprintf(stderr, "[dji_rc] 所有串口打开失败,退出\n");
        return 1;
    }
    // PB6 检测: 接地 → UART0 留给 debug 串口, 不输出协议
    g_pb6_debug = pb6_grounded();
    if (g_pb6_debug) {
        std::printf("[dji_rc] PB6 接地 → debug 模式, 跳过协议输出 (UART0 供 console/getty)\n");
        std::fflush(stdout);
        getty_start();
    }

    // 协议输出 (UART0): SBUS 标准=100k 8E2, SBUS 非标=115200 8N1, CRSF=420k 8N1
    bool out_even2 = (out_mode == 's') && g_sbus_std;
    if (!g_pb6_debug) {
        int newFd = uart_open_out(out_dev, out_baud, out_even2);
        g_out_fd.store(newFd);   // C1: atomic store
        if (newFd < 0) {
            std::fprintf(stderr, "[dji_rc] 输出口打开失败: %s @%d\n", out_dev, out_baud);
        } else {
            std::printf("[dji_rc] 输出 %c: %s @%d %s fd=%d (通道映射 %s)\n",
                        out_mode, out_dev, out_baud, out_even2 ? "8E2" : "8N1", newFd,
                        g_ch_map_valid.load() ? "custom" : "default");
        }
    }
    sockaddr_in rcmsg_dst;
    int rcmsg_fd = rcmsg_open(rcmsg_host, rcmsg_port, &rcmsg_dst);
    uint32_t rcmsg_seq = 0;

    // 回传 UDP (CRSF 模式)
    sockaddr_in tlm_dst;
    int tlm_fd = -1;
    if (out_mode == 'c' && g_crsf_telem) {
        tlm_fd = rcmsg_open(rcmsg_host, TLM_PORT, &tlm_dst);
        g_tlm_fd = tlm_fd;
    }

    // 启动接收线程 (协议输出在 P20 rx_thread 的 handle_pkt 里事件驱动)
    std::thread t1, t2, t3, t4;
    crsf_params_init();   /* 初始化 CRSF 参数表 (Device_Ping 响应用) */
    if (g_p20.fd >= 0) t1 = std::thread(rx_thread, &g_p20);
    if (g_p0.fd  >= 0) t2 = std::thread(rx_thread, &g_p0);
    if (out_mode == 'c' && g_crsf_telem && g_out_fd.load() >= 0)
        t3 = std::thread(crsf_rx_thread);
    if (g_crsf_bridge && g_out_fd >= 0)
        t4 = std::thread(crsf_bridge_rx_thread);   /* bridge 下行: 网口 → UART0 */

    // 主循环: 状态文件写入 + 控制台打印 (SBUS/CRSF 输出走独立事件驱动)
    std::printf("[dji_rc] Ctrl+C 停止\n\n");
    while (!g_stop.load(std::memory_order_relaxed)) {
        struct timespec ts = {0, interval_ms * 1000000L};
        nanosleep(&ts, nullptr);

        rc_state_t s20, s0;
        uint32_t g20, g0, rx20, rx0;
        int64_t l20, l0;

        g_mtx.lock();
        s20 = g_p20.state; g20 = g_p20.good; rx20 = g_p20.rx_bytes; l20 = g_p20.last_us;
        s0  = g_p0.state;  g0  = g_p0.good;  rx0  = g_p0.rx_bytes;  l0  = g_p0.last_us;
        g_mtx.unlock();

        int64_t n = now_us();
        int64_t age20 = (s20.type == RC_NONE) ? INT64_MAX : n - l20;
        int64_t age0  = (s0.type  == RC_NONE) ? INT64_MAX : n - l0;

        rc_state_t m;
        rc_merge(&s20, age20, &s0, age0, 500000LL, &m);  // 500ms stale

        if (m.type != RC_NONE) {
            // 状态文件 (供 web_server /api/rc)
            write_state_file(m, g20, g0, rx20, rx0, now_us());
            send_rcmsg(rcmsg_fd, rcmsg_dst, m, true, ++rcmsg_seq, n);
        } else if (rx20 > 0 || rx0 > 0) {
            // UART有数据但RC掉线: 写空状态防旧数据残留
            static const char no_rc[] = "{\"error\":\"no RC data\",\"rx1\":%u,\"rx2\":%u}\n";
            char buf[128];
            int w = snprintf(buf, sizeof(buf), no_rc, rx20, rx0);
            int fd = ::open("/var/log/rc_state.json.tmp", O_WRONLY | O_CREAT | O_TRUNC, 0644);
            if (fd >= 0) {
                if (::write(fd, buf, w) == w)
                    ::rename("/var/log/rc_state.json.tmp", "/var/log/rc_state.json");
                ::close(fd);
            }
            send_rcmsg(rcmsg_fd, rcmsg_dst, m, false, ++rcmsg_seq, n);
        }

        // CRSF 回传: 有回传数据时发 tlm UDP (65531) + 写状态文件
        if (g_out_mode.load() == 'c') {
            crsf_telem_t telem;
            g_mtx.lock(); telem = g_telem; g_mtx.unlock();
            if (telem.last_rx_us > 0 && (n - (int64_t)telem.last_rx_us) < 1000000LL) {
                if (tlm_fd >= 0) send_tlm(tlm_fd, tlm_dst, telem);
                write_telem_file(telem);
            }
        }

        // 每 2s 检测输出配置变化 (web_server 保存后进程内热重配, 避免 execv 崩溃)
        // bridge 模式: 保持 CRSF bridge 配置, 跳过 SPI config 热重配
        static int64_t last_cfg_check = 0;
        if (!g_crsf_bridge && n - last_cfg_check > 2000000LL) {
            last_cfg_check = n;
            char cm; int cb; bool cs;
            // DBG#baud: 记录 load_rc_output_cfg 读取结果, 定位热重配为何不触发
            bool cfgOk = load_rc_output_cfg(cm, cb, cs);
            if (cfgOk) {
                bool diff = (cm != g_out_mode.load() || cb != g_out_baud.load() || cs != g_sbus_std);
                std::printf("[dji_rc][dbg] cfg chk: ok=%d cur=%c/%d/%d spi=%c/%d/%d diff=%d\n",
                            cfgOk ? 1 : 0,
                            g_out_mode.load(), g_out_baud.load(), g_sbus_std ? 1 : 0,
                            cm, cb, cs ? 1 : 0, diff ? 1 : 0);
                std::fflush(stdout);
            }
            if (cfgOk &&
                (cm != g_out_mode.load() || cb != g_out_baud.load() || cs != g_sbus_std)) {
                std::printf("[dji_rc] 输出配置变化 mode=%c baud=%d sbus_std=%d → 热重配\n",
                            cm, cb, cs ? 1 : 0);
                std::fflush(stdout);
                bool oldCrsf = (g_out_mode.load() == 'c');
                g_out_mode.store(cm); g_out_baud.store(cb); g_sbus_std = cs;   // C1: atomic store

                /* 先安全停掉旧回传线程 (CRSF->任何 或 任何->CRSF 切换) */
                if (t3.joinable()) {
                    g_crsf_stop.store(true);
                    /* 关闭 fd 使阻塞的 read 立即返回 */
                    int oldFd = g_out_fd.exchange(-1);   // C1: atomic
                    if (oldFd >= 0) { ::close(oldFd); }
                    t3.join();
                    g_crsf_stop.store(false);
                }
                /* 重开输出 fd: SBUS标准=8E2, SBUS非标=8N1, CRSF=8N1 */
                bool even2 = (g_out_mode.load() == 's') && g_sbus_std;
                if (g_out_fd.load() < 0)
                    g_out_fd.store(uart_open_out(out_dev, g_out_baud.load(), even2));   // C1: atomic
                if (g_out_fd.load() < 0)
                    std::fprintf(stderr, "[dji_rc] 热重配输出打开失败\n");

                /* CRSF 模式启动回传线程 */
                if (g_out_mode.load() == 'c' && g_crsf_telem && g_out_fd.load() >= 0 && !t3.joinable()) {
                    g_crsf_stop.store(false);
                    t3 = std::thread(crsf_rx_thread);
                }
                (void)oldCrsf;
            }
        }

        // PB6 运行中自动切换 (每 2s 检测, 连续 3 次防抖)
        static int64_t last_pb6 = 0;
        if (n - last_pb6 > 2000000LL) {
            last_pb6 = n;
            bool gnd = pb6_grounded();
            pb6_auto_switch(gnd, out_dev, out_mode, out_baud, g_pb6_debug, t3);
        }

        // 控制台打印
        char line[256];
        line[0] = '\0';
        if (m.type == RC_NONE) {
            snprintf(line, sizeof(line), "no-RC rx1=%u rx2=%u", rx20, rx0);
        } else {
            rc_state_to_kv(&m, line, sizeof(line));
        }
        std::printf("[dji_rc] %s | g1=%u g2=%u rx1=%u rx2=%u\n", line, g20, g0, rx20, rx0);
        if (debug_uart0 && (n - g_last_debug_us) >= 5000000LL) {
            debug_log("[dji_rc][dbg] %s g1=%u g2=%u rx1=%u rx2=%u age1=%lld age2=%lld",
                      line, g20, g0, rx20, rx0, (long long)age20, (long long)age0);
            g_last_debug_us = n;
        }
    }

    g_stop.store(true);
    g_crsf_stop.store(true);
    /* 先关闭 fd 唤醒阻塞的 read, 再 join, 避免死锁 */
    if (g_p20.fd >= 0) { ::close(g_p20.fd); g_p20.fd = -1; }
    if (g_p0.fd  >= 0) { ::close(g_p0.fd);  g_p0.fd  = -1; }
    int outFdClean = g_out_fd.exchange(-1);   // C1: atomic
    if (outFdClean >= 0) { ::close(outFdClean); }
    if (t3.joinable()) t3.join();
    if (t4.joinable()) t4.join();   /* bridge 下行线程 */
    if (t1.joinable()) t1.join();
    if (t2.joinable()) t2.join();
    if (g_debug_fd >= 0) ::close(g_debug_fd);
    if (rcmsg_fd >= 0) ::close(rcmsg_fd);
    if (tlm_fd >= 0) ::close(tlm_fd);
    return 0;
}
