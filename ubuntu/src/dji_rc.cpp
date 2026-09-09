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
#include <cstdarg>
#include <cstdio>
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
#include "rc_source_select.h"

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
static rc_state_t g_app_rc; // App 侧 getevent+40007 融合后的 RCM1 状态
static uint32_t g_app_good = 0;
static uint32_t g_app_rx = 0;
static int64_t g_app_last_us = 0;
static std::mutex g_mtx;
static std::atomic<bool> g_stop{false};
static std::atomic<bool> g_crsf_stop{false};   /* 独立控制 CRSF 回传线程 (t3), 不干扰 t1/t2 */
static std::atomic<bool> g_bridge_stop{false}; /* 独立控制 bridge 下行线程 (t4), 避免与 t3 的 g_crsf_stop 互相干扰 */

static int64_t now_us();   /* forward */
static constexpr int64_t P20_PRIORITY_US = 50000LL;
static constexpr int64_t RC_STALE_US = 500000LL;

/* ── Lua 发送缓冲 (单帧, 模仿 EdgeTX outputTelemetryBuffer) ──
 * CRSF Lua 帧与通道帧是时分复用: Lua 帧替代通道帧发送, 不叠加。
 * bridge 收到 Lua 命令 → 存此单帧缓冲 (2s 超时丢弃, 像 EdgeTX);
 * 每拍发送时: 有 Lua 帧则发 Lua, 否则发通道帧。 */
/* Lua 帧多帧队列 (最多 4 帧): App 的 fieldPopup 可能持续发 lcsQuery(0x2D),
 * 原单帧缓冲会被覆盖导致参数请求(0x2C)丢失。队列保证各帧依次发出。 */
static uint8_t   g_lua_q[4][64];
static uint8_t   g_lua_qlen[4];
static int       g_lua_qh = 0;   /* 队头 (待发) */
static int       g_lua_qt = 0;   /* 队尾 (入队) */
static std::mutex g_tx_mtx;

static void tx_lua_enqueue(const uint8_t *data, size_t len) {
    if (len == 0 || len > 64) return;
    std::lock_guard<std::mutex> lock(g_tx_mtx);
    memcpy(g_lua_q[g_lua_qt], data, len);
    g_lua_qlen[g_lua_qt] = (uint8_t)len;
    g_lua_qt = (g_lua_qt + 1) % 4;
    if (g_lua_qt == g_lua_qh) g_lua_qh = (g_lua_qh + 1) % 4;  /* 满则覆盖最旧 */
}

/* 取待发 Lua 帧 (队列先进先出)。 */
static size_t tx_lua_take(uint8_t *out, size_t max) {
    std::lock_guard<std::mutex> lock(g_tx_mtx);
    if (g_lua_qh == g_lua_qt) return 0;
    size_t n = g_lua_qlen[g_lua_qh] < max ? g_lua_qlen[g_lua_qh] : max;
    memcpy(out, g_lua_q[g_lua_qh], n);
    g_lua_qh = (g_lua_qh + 1) % 4;
    return n;
}

/* UART0 debug 日志 (--debug-uart0 启用): 状态/输出行镜像到独立串口。
 * 来自 merge codex/adb-getevent-rc-fusion 的 UART0 调试子系统。 */
static int g_debug_fd = -1;
static int64_t g_last_debug_us = 0;
static void debug_log(const char *fmt, ...);   /* forward: 定义在 helpers */

// ── 输出 (SBUS/CRSF @SC16IS752 UART-A) ──
// C1: g_out_fd 被多线程 (rx_thread/t3/主线程) 无锁访问, 用 atomic 避免 fd 值撕裂
static std::atomic<int> g_out_fd{-1};
static std::atomic<char> g_out_mode{'s'}; // 's' = SBUS, 'c' = CRSF
static std::atomic<int>  g_out_baud{100000}; // 实际波特率 (SBUS标准=100000, SBUS非标=115200, CRSF=115200)
static bool g_sbus_std = true;          // SBUS 标准模式: true=100k 8E2, false=115200 8N1
static std::mutex g_out_write_mtx;        // CO-4: 保护对 g_out_fd 的写 (out_send + crsf_rx_thread 并发)
static std::atomic<uint32_t> g_tx_ok{0};
static std::atomic<uint32_t> g_tx_err{0};

static int uart_open_out(const char *dev, int baud, bool even2);   /* forward */
static void aux_tmux_set(int normal_rx_en, int tx_bus_en, int crsf_rx_en, int sbus_tx_en);  /* forward: TMUX1511 (定义在文件中部) */
static const char *g_out_dev = "/dev/ttySC0";  /* 协议输出口, tx_recover 重开用 */

static bool out_dev_is_sc16(const char *dev) {
    return dev != nullptr && std::strstr(dev, "/dev/ttySC") != nullptr;
}

/* 扩展 UART 硬件卡死自动恢复: 写连续失败 N 次 → 重开输出口。 */
static void tx_recover(void) {
    bool even2 = (g_out_mode.load() == 's') && g_sbus_std;
    int oldFd = g_out_fd.exchange(-1);   // C1: atomic 取走旧 fd
    if (oldFd >= 0) { ::close(oldFd); }
    int newFd = uart_open_out(g_out_dev, g_out_baud.load(), even2);
    g_out_fd.store(newFd);   // C1: atomic
    std::printf("[dji_rc] 扩展 UART 卡死自动恢复: 旧fd=%d 新fd=%d @%d\n",
                oldFd, newFd, g_out_baud.load());
    std::fflush(stdout);
}

/* 等 TX FIFO 空: 半双工切回 RX 前必须确保帧已物理发出, 否则 TMUX 切走会截断。
 * TIOCOUTQ 返回未发送字节数, 轮询到 0 或超时 (最多 ~20ms)。 */
static void uart_drain_tx(int fd) {
    for (int i = 0; i < 40; i++) {
        int outq = 0;
        if (ioctl(fd, TIOCOUTQ, &outq) < 0 || outq <= 0) return;
        ::usleep(500);
    }
}

/* 写扩展 UART + 卡死检测: 连续失败 TX_ERR_LIMIT 次 → 自动重开。
 * TMUX1511 模式由 aux_tmux_apply 统一设置。
 * CRSF 基线保持 TX_BUS_EN + CRSF_RX_EN, 每帧不重复 mmap /dev/mem 切换。
 * 调用方须持 g_out_write_mtx。返回写是否成功。 */
static bool tx_write_uart(int fd, const uint8_t *data, size_t len) {
    static int err_cnt = 0;
    const int TX_ERR_LIMIT = 50;   /* 连续 50 次写失败(约数百 ms)判 UART0 卡死 */
    bool crsf = (g_out_mode.load() == 'c');
    ssize_t w = ::write(fd, data, len);
    if (w != (ssize_t)len) {
        err_cnt++;
        std::printf("[dji_rc] 扩展 UART 写 %zu 得 %zd errno=%d(%s) err_cnt=%d\n",
                    len, w, errno, std::strerror(errno), err_cnt);
        std::fflush(stdout);
        if (err_cnt >= TX_ERR_LIMIT) {
            err_cnt = 0;
            tx_recover();   /* 自动重开 UART0 */
        }
        return false;
    }
    err_cnt = 0;
    if (crsf) {
        uart_drain_tx(fd);                    /* 等帧物理发完 */
    }
    return true;
}

static bool g_crsf_telem = true;        // CRSF 是否接收回传
static std::atomic<bool> g_ch_map_valid{false};  // CRIT#2: atomic, 主线程热重配写 + rx_thread 读
static uint8_t g_ch_map[CH_COUNT];      // 通道映射表 (读写受 g_mtx 保护)
static crsf_telem_t g_telem;            // 最近回传数据 (CRSF 回传线程写)
static bool g_ch_lock[CH_COUNT] = {};
static bool g_lock_state[CH_COUNT] = {};
static bool g_lock_prev_high[CH_COUNT] = {};
static uint16_t g_lock_on_value[CH_COUNT] = {};
static uint16_t g_lock_off_value[CH_COUNT] = {};
static std::mutex g_lock_mtx;
// ── 长按触发 (每源按下起始时间; 0 = 未按下) ──
static constexpr int64_t LP_THRESHOLD_US = 500000;   // 长按确认阈值 500ms
static int64_t g_lp_press_us[SRC_COUNT] = {};        // 读写受 g_mtx 保护 (build_output_channels 内)

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

static int uart_open_out(const char *dev, int baud, bool even2);   /* forward */
static void crsf_rx_thread();                                       /* forward */
static void crsf_bridge_rx_thread();                                /* forward */

// CRSF 桥开关 (crsf-bridge 模式)
static std::atomic<bool> g_crsf_bridge{false};   // atomic: 主线程写, rx/crsf_rx 线程读

// ── TMUX1511 模式控制 (PB2-PB5) ─────────────────────────────
// PB2=NORMAL_RX_EN, PB3=TX_BUS_EN, PB4=CRSF_RX_EN, PB5=SBUS_TX_EN
// sun8i-v3s pinctrl @0x01C20800 (mmap 页对齐 0x01C20000 + 页内偏移 0x800):
//   每 CFG 寄存器管 8 引脚, 每引脚 4 位 (V3s 实测, 非 4 引脚/寄存器):
//     PB_CFG0 @0x24 (PB0-7): PB2=bit8-11, PB3=bit12-15, PB4=bit16-19, PB5=bit20-23 (值 1=输出)
//     PB_CFG1 @0x28 (PB8-15): 含 UART0 的 PB8/PB9 —— 严禁写!
//       旧代码误当 PB_CFG1(PB4-7), 把 PB8/PB9 配成 GPIO 输出, 导致 UART0 debug 串口物理断连
//     PB_DATA @0x34 (PB0-31): PB2=bit2, PB3=bit3, PB4=bit4, PB5=bit5
// TMUX1511 = 4×SPST 独立模拟开关, 各通道可同时导通 (TI 数据手册 SCDS390)。
// 互斥约束 (原理图规则, 防总线/接收冲突):
//   - TX_BUS_EN 与 SBUS_TX_EN 互斥 (两个 TX 不能同时接共享 TXD/BUS)
//   - NORMAL_RX_EN 与 CRSF_RX_EN 互斥 (两个 RX 不能同时接 SC16 RX)
static void aux_tmux_set(int normal_rx_en, int tx_bus_en, int crsf_rx_en, int sbus_tx_en)
{
    const uintptr_t PIO_PHYS = 0x01C20800u;
    const uintptr_t BASE     = PIO_PHYS & ~0xFFFu;   /* 页对齐 0x01C20000 */
    const uintptr_t PAGE_OFF = PIO_PHYS - BASE;      /* 0x800 页内偏移 */
    const size_t    PG       = (size_t)sysconf(_SC_PAGESIZE);

    int memfd = ::open("/dev/mem", O_RDWR | O_SYNC);
    if (memfd < 0) {
        std::fprintf(stderr, "[dji_rc] TMUX: /dev/mem 打开失败 (%s)\n", std::strerror(errno));
        return;
    }
    void *map = mmap(NULL, PG, PROT_READ | PROT_WRITE, MAP_SHARED, memfd, (off_t)BASE);
    ::close(memfd);
    if (map == MAP_FAILED) {
        std::fprintf(stderr, "[dji_rc] TMUX: mmap 失败 (%s)\n", std::strerror(errno));
        return;
    }
    uint8_t *pio = (uint8_t *)map + PAGE_OFF;
    volatile uint32_t *cfg0 = (volatile uint32_t *)(pio + 0x24);  /* PB_CFG0 (PB0-7) */
    volatile uint32_t *data = (volatile uint32_t *)(pio + 0x34);  /* PB_DATA (PB0-31) */

    /* 1. 配 PB2-PB5 为输出 (CFG 值 01), 全部在 PB_CFG0 (0x24) */
    uint32_t c0 = *cfg0;
    c0 = (c0 & ~(0xFu << 8)) | (0x1u << 8);    /* PB2 */
    c0 = (c0 & ~(0xFu << 12)) | (0x1u << 12);  /* PB3 */
    c0 = (c0 & ~(0xFu << 16)) | (0x1u << 16);  /* PB4 */
    c0 = (c0 & ~(0xFu << 20)) | (0x1u << 20);  /* PB5 */
    *cfg0 = c0;

    /* 2. 写 DATA bit2-5 (PB2-5 电平) */
    uint32_t d = *data;
    d &= ~((1u << 2) | (1u << 3) | (1u << 4) | (1u << 5));
    d |= (normal_rx_en ? 1u : 0u) << 2;
    d |= (tx_bus_en ? 1u : 0u) << 3;
    d |= (crsf_rx_en ? 1u : 0u) << 4;
    d |= (sbus_tx_en ? 1u : 0u) << 5;
    *data = d;
    ::usleep(10);    /* 等寄存器生效 (半双工切换须快, 帧间切换占帧间时间) */

    ::munmap(map, PG);
    std::printf("[dji_rc] TMUX: N=%d T=%d C=%d S=%d\n",
                normal_rx_en, tx_bus_en, crsf_rx_en, sbus_tx_en);
    std::fflush(stdout);
}

/* 按 dji_rc 运行模式设置 TMUX1511 基线 (发送时的 TX/RX 切换由 tx_write_uart 处理):
 *   SBUS (out_mode=='s') : (0,0,0,1) SBUS_TX_EN=1, 反相单线输出 (只发不收)
 *   CRSF (out_mode=='c') : (0,0,1,0) CRSF_RX_EN=1 接收态基线; 每次发帧 tx_write_uart
 *     切 TX_BUS_EN=1, 帧发完 (drain) 切回 CRSF_RX_EN=1 — 4 模式互斥 (老大定):
 *       SBUS=(0,0,0,1) / CRSF TX=(0,1,0,0) / CRSF RX=(0,0,1,0) / 全双工=(1,1,0,0) */
static void aux_tmux_apply()
{
    if (g_out_mode.load() == 's') {
        aux_tmux_set(0, 0, 0, 1);   /* SBUS: SBUS_TX_EN=1 */
    } else {
        /* CRSF: 基线保持 TX_BUS_EN + CRSF_RX_EN (0,1,1,0).
         * 实测 SC16 UART A RX 走 TX_BUS_EN 通路, 仅 CRSF_RX_EN(0,0,1,0) 时 RX 断,
         * ELRS 全双工响应收不到. 保持 TX_BUS_EN 使 RX 一直通。 */
        aux_tmux_set(0, 1, 1, 0);
    }
}

// ── rcmsg (RC 数据 UDP) ──
static constexpr uint32_t RCMSG_MAGIC = 0x314D4352u;  // "RCM1", little-endian on wire
static constexpr int RCMSG_PORT = 65530;
static constexpr int APP_RC_PORT = 65531;
// 手机主地址 10.0.0.2 (Android VpnService 只对主地址投递 protect 隧道包)。
// V3s 把电脑发的 144.11 包 DNAT 到 10.0.0.2, 手机在此收 rcmsg/局域网入向。
static constexpr const char *RCMSG_HOST = "10.0.0.2";

// ── CRSF 桥 (crsf-bridge 模式): SC16IS752 CRSF 帧 ↔ 网口 UDP 透明转发 ──
// App 跑 ELRS Lua 脚本, 经网口 UDP 发 CRSF 参数命令, V3s 转 SC16IS752。
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

// ═══════════════════════════════════════════════════════════════════════
// helpers
// ═══════════════════════════════════════════════════════════════════════

static int64_t now_us() {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    // CRIT#1: 用 1000000LL, 避免 32-bit ARM 上 ts.tv_sec*1000000 (long) 35分钟溢出回卷
    return (int64_t)ts.tv_sec * 1000000LL + ts.tv_nsec / 1000;
}

/* UART0 debug 输出口: --debug-uart0 启用后, 状态/输出行镜像写独立串口 (默认 /dev/ttyS0)。 */
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
    /* L1~R3 (bit 15-20): App 融合 getevent KEY_F1..F6, 供 SRC_LR 6 档互斥自锁 */
    if (st.l1)       b |= 1u << 15;
    if (st.l2)       b |= 1u << 16;
    if (st.l3)       b |= 1u << 17;
    if (st.r1)       b |= 1u << 18;
    if (st.r2)       b |= 1u << 19;
    if (st.r3)       b |= 1u << 20;
    return b;
}

static bool rcmsg_to_state(const RcMsg &msg, rc_state_t *out)
{
    if (!out) return false;
    if (msg.magic != RCMSG_MAGIC || msg.version != 1 || msg.size != sizeof(RcMsg)) return false;
    std::memset(out, 0, sizeof(*out));
    out->type = RC_APP_FUSED;
    for (int i = 0; i < 6; i++) out->ch[i] = msg.raw_ch[i];
    uint32_t b = msg.buttons;
    out->btn      = (b >> 0) & 1u;
    out->stop     = (b >> 1) & 1u;
    out->focus    = (b >> 2) & 1u;
    out->shot     = (b >> 3) & 1u;
    out->rec      = (b >> 4) & 1u;
    out->rth      = (b >> 5) & 1u;
    out->c1       = (b >> 6) & 1u;
    out->c2       = (b >> 7) & 1u;
    out->c3       = (b >> 8) & 1u;
    out->up       = (b >> 9) & 1u;
    out->down     = (b >> 10) & 1u;
    out->left     = (b >> 11) & 1u;
    out->right    = (b >> 12) & 1u;
    out->aircraft = (b >> 13) & 1u;
    out->back     = (b >> 14) & 1u;
    out->l1       = (b >> 15) & 1u;
    out->l2       = (b >> 16) & 1u;
    out->l3       = (b >> 17) & 1u;
    out->r1       = (b >> 18) & 1u;
    out->r2       = (b >> 19) & 1u;
    out->r3       = (b >> 20) & 1u;
    out->mode = (msg.mode == 'S' || msg.mode == 'N' || msg.mode == 'F') ? (char)msg.mode : '?';
    out->dial = msg.dial;
    return true;
}

static void build_output_channels(const rc_state_t &st, uint16_t ch[CH_COUNT], bool advance_latch);

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
    /* latch 由主循环的统一 RC 状态推进；rcmsg 只应用当前 latch，避免重复 toggle。 */
    build_output_channels(src, msg.ch, false);
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

static void output_from_input_event(DjiPort *p);  // forward: 定义在输出区域

static bool handle_pkt(DjiPort *p, const duml_pkt_t *pk)
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
    return ok;
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
            bool rc_ok = handle_pkt(p, &pk);
            g_mtx.unlock();
            if (rc_ok) output_from_input_event(p);
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

// ── App 融合 RC 接收线程: Android 侧按 20ms 定时发 RCM1 到 65531 ──────

static void app_rc_thread()
{
    int fd = ::socket(AF_INET, SOCK_DGRAM, 0);
    if (fd < 0) {
        std::fprintf(stderr, "[dji_rc] app_rc socket failed: %s\n", std::strerror(errno));
        return;
    }
    int one = 1;
    ::setsockopt(fd, SOL_SOCKET, SO_REUSEADDR, &one, sizeof(one));
    struct timeval tv;
    tv.tv_sec = 0;
    tv.tv_usec = 200000;
    ::setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));

    sockaddr_in addr{};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(APP_RC_PORT);
    addr.sin_addr.s_addr = INADDR_ANY;
    if (::bind(fd, (sockaddr *)&addr, sizeof(addr)) < 0) {
        std::fprintf(stderr, "[dji_rc] app_rc bind :%d failed: %s\n",
                     APP_RC_PORT, std::strerror(errno));
        ::close(fd);
        return;
    }
    std::printf("[dji_rc] app_rc UDP listen :%d fd=%d\n", APP_RC_PORT, fd);

    while (!g_stop.load(std::memory_order_relaxed)) {
        RcMsg msg{};
        ssize_t n = ::recv(fd, &msg, sizeof(msg), 0);
        if (n < 0) {
            if (errno == EAGAIN || errno == EWOULDBLOCK || errno == EINTR) continue;
            std::fprintf(stderr, "[dji_rc] app_rc recv error: %s\n", std::strerror(errno));
            break;
        }
        g_mtx.lock();
        g_app_rx += (uint32_t)n;
        rc_state_t st;
        if (n == (ssize_t)sizeof(msg) && rcmsg_to_state(msg, &st)) {
            g_app_rc = st;
            g_app_good++;
            g_app_last_us = now_us();
        }
        g_mtx.unlock();
    }
    ::close(fd);
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

static void write_text_atomic(const char *path, const char *buf, int len)
{
    char tmp[128];
    snprintf(tmp, sizeof(tmp), "%s.tmp", path);
    int fd = ::open(tmp, O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fd < 0) return;

    ssize_t written = ::write(fd, buf, len);
    ::close(fd);
    if (written == len)
        ::rename(tmp, path);
    else
        std::fprintf(stderr, "[dji_rc] state write %s: wrote %zd of %d\n", path, written, len);
}

static void write_state_file(const rc_state_t &st, const char *active_src,
                             uint32_t g1, uint32_t g2,
                             uint32_t rx1, uint32_t rx2,
                             uint32_t app_good, uint32_t app_rx,
                             int64_t app_age_us, bool app_primary,
                             int64_t ts_us)
{
    uint16_t ch[CH_COUNT];
    /* latch 由主循环的统一 RC 状态推进；状态文件只应用当前 latch。 */
    build_output_channels(st, ch, false);

    static int64_t prev_us = 0;
    static uint32_t prev_g1 = 0, prev_g2 = 0, prev_rx1 = 0, prev_rx2 = 0, prev_tx_ok = 0;
    static uint32_t out_count = 0;
    static double good1_hz = 0.0, good2_hz = 0.0, rx1_bps = 0.0, rx2_bps = 0.0, out_hz = 0.0, tx_hz = 0.0;
    uint32_t tx_ok = g_tx_ok.load();
    uint32_t tx_err = g_tx_err.load();

    out_count++;
    if (prev_us == 0) {
        prev_us = ts_us;
        prev_g1 = g1; prev_g2 = g2; prev_rx1 = rx1; prev_rx2 = rx2; prev_tx_ok = tx_ok;
    } else {
        int64_t elapsed_us = ts_us - prev_us;
        if (elapsed_us >= 1000000LL) {
            double sec = elapsed_us / 1000000.0;
            good1_hz = (g1 - prev_g1) / sec;
            good2_hz = (g2 - prev_g2) / sec;
            rx1_bps = (rx1 - prev_rx1) / sec;
            rx2_bps = (rx2 - prev_rx2) / sec;
            out_hz = out_count / sec;
            tx_hz = (tx_ok - prev_tx_ok) / sec;
            prev_us = ts_us;
            prev_g1 = g1; prev_g2 = g2; prev_rx1 = rx1; prev_rx2 = rx2; prev_tx_ok = tx_ok;
            out_count = 0;
        }
    }

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
        "\"l1\":%d,\"l2\":%d,\"l3\":%d,\"r1\":%d,\"r2\":%d,\"r3\":%d,\"lr_pos\":%d,"
        "\"good1\":%u,\"good2\":%u,\"rx1\":%u,\"rx2\":%u,"
        "\"good1_hz\":%.1f,\"good2_hz\":%.1f,\"rx1_bps\":%.1f,\"rx2_bps\":%.1f,\"out_hz\":%.1f,"
        "\"tx_hz\":%.1f,\"tx_ok\":%u,\"tx_err\":%u,\"active_src\":\"%s\","
        "\"app_rc_good\":%u,\"app_rc_rx\":%u,\"app_rc_age_ms\":%lld,"
        "\"rc_input_primary\":\"%s\","
        "\"type\":\"%s\",\"ts_us\":%lld}\n",
        ch[0], ch[1], ch[2], ch[3], ch[4], ch[5], ch[6], ch[7],
        ch[8], ch[9], ch[10], ch[11], ch[12], ch[13], ch[14], ch[15],
        st.ch[0], st.ch[1], st.ch[2], st.ch[3], st.ch[4], st.ch[5],
        st.mode, st.btn, st.stop, st.focus, st.shot, st.rec,
        st.rth, st.c1, st.c2, st.c3, st.dial,
        st.up, st.down, st.left, st.right, st.aircraft, st.back,
        st.l1, st.l2, st.l3, st.r1, st.r2, st.r3, g_lr_pos,
        g1, g2, rx1, rx2,
        good1_hz, good2_hz, rx1_bps, rx2_bps, out_hz,
        tx_hz, tx_ok, tx_err, active_src ? active_src : "none",
        app_good, app_rx,
        (long long)((app_age_us == INT64_MAX) ? -1 : app_age_us / 1000),
        app_primary ? "android_rcm1" : "uart_fallback",
        rc_type_name(st.type),
        (long long)ts_us);

    // atomic write: tmp → rename
    // H: snprintf 返回值可能超过 sizeof(buf) 或为负, clamp 避免越界写
    if (w < 0) w = 0;                       // 复审: 负值(编码错误) → 0
    if (w > (int)sizeof(buf)) w = (int)sizeof(buf);
    write_text_atomic("/tmp/rc_state.json", buf, w);
    write_text_atomic("/var/log/rc_state.json", buf, w);
}

// ── 协议输出: P20 每解一帧就立刻发 (SBUS/CRSF 由 g_out_mode 决定) ──────

static bool src_lockable(rc_src_t s)
{
    switch (s) {
        case SRC_REC: case SRC_RTH: case SRC_STOP: case SRC_FOCUS:
        case SRC_C1: case SRC_C2: case SRC_C3:
        case SRC_AIRCRAFT: case SRC_BACK: case SRC_BTN:
        case SRC_UP: case SRC_DOWN: case SRC_LEFT: case SRC_RIGHT:
            return true;
        default:
            return false;
    }
}

static bool src_lock_active(const rc_state_t &st, rc_src_t s)
{
    /* 配置长按的源: 未确认(按住不足500ms)不算按下, 短按不 toggle 自锁 latch */
    if (rc_cfg_lp(s) && !rc_map_lp_get(s)) return false;
    switch (s) {
        case SRC_REC: return st.rec != 0;
        case SRC_RTH: return st.rth != 0;
        case SRC_STOP: return st.stop != 0;
        case SRC_FOCUS: return st.focus != 0;
        case SRC_C1: return st.c1 != 0;
        case SRC_C2: return st.c2 != 0;
        case SRC_C3: return st.c3 != 0;
        case SRC_AIRCRAFT: return st.aircraft != 0;
        case SRC_BACK: return st.back != 0;
        case SRC_BTN: return st.btn != 0;
        case SRC_UP: return st.up != 0;
        case SRC_DOWN: return st.down != 0;
        case SRC_LEFT: return st.left != 0;
        case SRC_RIGHT: return st.right != 0;
        default: return false;
    }
}

static void apply_channel_locks(const rc_state_t &st, uint16_t ch[CH_COUNT],
                                const uint8_t map[CH_COUNT], const bool locks[CH_COUNT],
                                bool advance_latch)
{
    std::lock_guard<std::mutex> lock(g_lock_mtx);
    for (int i = 0; i < CH_COUNT; i++) {
        rc_src_t src = (rc_src_t)map[i];
        bool enabled = locks[i] && src_lockable(src);
        if (!enabled) {
            g_lock_state[i] = false;
            g_lock_prev_high[i] = false;
            g_lock_on_value[i] = 0;
            g_lock_off_value[i] = 0;
            continue;
        }
        bool high = src_lock_active(st, src);
        if (advance_latch) {
            if (high) g_lock_on_value[i] = ch[i];
            else g_lock_off_value[i] = ch[i];
            if (high && !g_lock_prev_high[i]) g_lock_state[i] = !g_lock_state[i];
            g_lock_prev_high[i] = high;
        }
        uint16_t onValue = g_lock_on_value[i] ? g_lock_on_value[i] : ch[i];
        uint16_t offValue = g_lock_off_value[i] ? g_lock_off_value[i] : ch[i];
        ch[i] = g_lock_state[i] ? onValue : offValue;
    }
}

/* 长按计时: 对配置为长按(rc_cfg_lp)的按键源, 按住 ≥500ms 置确认 (rc_map_lp_set true),
 * 松开置 false。仅更新确认状态, 不改 st — 复合源 (C12/SHOT/DIR) 读原始字段不受影响,
 * 独立按键源由 src_value 内部检查 g_lp_confirmed。须在 g_mtx 内调用 (读 g_cfg)。 */
static void update_long_press(const rc_state_t &st)
{
    int64_t now = now_us();
    struct LpSrc { rc_src_t s; uint8_t rc_state_t::*field; };
    static const LpSrc kLp[] = {
        {SRC_REC, &rc_state_t::rec}, {SRC_RTH, &rc_state_t::rth},
        {SRC_STOP, &rc_state_t::stop}, {SRC_FOCUS, &rc_state_t::focus},
        {SRC_C1, &rc_state_t::c1}, {SRC_C2, &rc_state_t::c2}, {SRC_C3, &rc_state_t::c3},
        {SRC_AIRCRAFT, &rc_state_t::aircraft}, {SRC_BACK, &rc_state_t::back},
        {SRC_BTN, &rc_state_t::btn}, {SRC_UP, &rc_state_t::up}, {SRC_DOWN, &rc_state_t::down},
        {SRC_LEFT, &rc_state_t::left}, {SRC_RIGHT, &rc_state_t::right},
    };
    for (const LpSrc &e : kLp) {
        bool pressed = (st.*(e.field)) != 0;
        if (pressed) {
            if (g_lp_press_us[e.s] == 0) g_lp_press_us[e.s] = now;   // 上升沿: 记起始
            bool confirmed = (now - g_lp_press_us[e.s] >= LP_THRESHOLD_US);
            rc_map_lp_set(e.s, confirmed);
        } else {
            g_lp_press_us[e.s] = 0;                  // 松开: 复位 + 清确认
            rc_map_lp_set(e.s, false);
        }
    }
}

/* L1~R3 互斥自锁推进: 任一按键按下沿 (0→1) → 切到对应档位 (直接选中, 互斥覆盖),
 * 松开保持 (自锁), 下次按其他键自动切档。档位存 g_lr_pos, src_value(SRC_LR) 输出其值。
 * 仅 App 融合 (RCM1) 有 l1..r3, 串口/DUML 路径这些字段恒 0, 不会误触发。 */
static void update_lr_latch(const rc_state_t &st)
{
    static uint8_t prev[6] = {};
    const uint8_t now[6] = { st.l1, st.l2, st.l3, st.r1, st.r2, st.r3 };
    for (int i = 0; i < 6; i++) {
        if (now[i] && !prev[i]) {   /* 按下沿: 切档 (互斥单选) */
            g_lr_pos = i;
            break;
        }
    }
    memcpy(prev, now, sizeof(prev));
}

static void build_output_channels(const rc_state_t &st, uint16_t ch[CH_COUNT], bool advance_latch)
{
    uint8_t mapSnap[CH_COUNT];
    bool lockSnap[CH_COUNT];
    rc_map_default(mapSnap);
    std::memset(lockSnap, 0, sizeof(lockSnap));
    {
        std::lock_guard<std::mutex> lock(g_mtx);
        if (g_ch_map_valid.load(std::memory_order_acquire)) std::memcpy(mapSnap, g_ch_map, CH_COUNT);
        std::memcpy(lockSnap, g_ch_lock, CH_COUNT);
        update_long_press(st);                       // 更新长按确认状态 (g_mtx 内, 读 g_cfg)
        if (advance_latch) update_lr_latch(st);      // 主循环推进 L1~R3 互斥自锁档位
        rc_map_build(&st, mapSnap, ch);              // 用原始 st: 复合源读原始字段, 独立源 src_value 内部检查确认
    }
    apply_channel_locks(st, ch, mapSnap, lockSnap, advance_latch);
}

static void advance_output_latches(const rc_state_t &st)
{
    uint16_t ch[CH_COUNT];
    build_output_channels(st, ch, true);
}

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
    /* latch 由主循环统一推进；串口输出只应用当前 latch。 */
    build_output_channels(m, ch, false);

    /* CRSF 时分复用: 有 Lua 帧待发 → 发 Lua (替代通道帧, EdgeTX 规范);
       否则发通道帧。直接写 UART0 (单一写者 out_send + 主循环 Lua 发送互斥)。 */
    if (outMode == 'c') {
        /* Lua 帧限流: 每 3 个 out_send 周期取一次 Lua (多帧队列), 其余发摇杆,
         * 保证摇杆 RC 帧(0x16)保底 2/3 输出。 */
        static int lua_counter = 0;
        uint8_t lua[64];
        size_t luaLen = 0;
        if (lua_counter % 3 == 0) luaLen = tx_lua_take(lua, sizeof(lua));
        lua_counter++;
        if (luaLen > 0) {
            /* Lua 帧优先: 替代本次通道帧 (限流后摇杆帧仍保底) */
            std::lock_guard<std::mutex> lock(g_out_write_mtx);
            if (g_out_fd.load() != outFd) return;
            if (!tx_write_uart(outFd, lua, luaLen)) { out_errors++; g_tx_err.fetch_add(1); }
            else { out_attempts++; g_tx_ok.fetch_add(1); }
        } else {
            uint8_t frame[CRSF_FRAME_MAX];
            int n = crsf_pack_channels(ch, frame);
            if (n > 0) {
                std::lock_guard<std::mutex> lock(g_out_write_mtx);
                if (g_out_fd.load() != outFd) return;
                if (!tx_write_uart(outFd, frame, (size_t)n)) { out_errors++; g_tx_err.fetch_add(1); }
                else { out_attempts++; g_tx_ok.fetch_add(1); }
            }
        }
    } else {
        uint8_t frame[SBUS_FRAME_LEN];
        sbus_encode(ch, frame);
        std::lock_guard<std::mutex> lock(g_out_write_mtx);
        if (g_out_fd.load() != outFd) return;
        if (!tx_write_uart(outFd, frame, SBUS_FRAME_LEN)) { out_errors++; g_tx_err.fetch_add(1); }
        else { out_attempts++; g_tx_ok.fetch_add(1); }
    }

    if (out_errors && out_attempts <= 10) {
        std::printf("[dji_rc] out fail attempts=%u errors=%u errno=%d\n", out_attempts, out_errors, errno);
    } else if ((out_attempts <= 10 || (out_attempts % 100) == 0) && out_errors == 0) {
        std::printf("[dji_rc] out ok mode=%c attempts=%u ch1=%u ch2=%u ch3=%u ch4=%u\n",
                    outMode, out_attempts, ch[0], ch[1], ch[2], ch[3]);
    }
}

/* 输入事件驱动输出: 921600 在 50ms 窗口内优先；超时后 115200 接管。 */
static void output_from_input_event(DjiPort *p)
{
    if (g_out_fd.load() < 0) return;   // C1: atomic load

    int64_t n = now_us();

    // CO-2/CO-3: 持锁拷贝 state, 避免与 P0 rx_thread / 主线程热重配的数据竞争
    rc_state_t s20, s0;
    int64_t l20, l0;
    g_mtx.lock();
    s20 = g_p20.state; l20 = g_p20.last_us;
    s0  = g_p0.state;  l0  = g_p0.last_us;
    g_mtx.unlock();

    int64_t age20 = (s20.type == RC_NONE) ? INT64_MAX : n - l20;
    int64_t age0  = (s0.type == RC_NONE) ? INT64_MAX : n - l0;

    RcSourceDecision d = rc_select_priority_source(s20, age20, s0, age0,
                                                   P20_PRIORITY_US, RC_STALE_US);
    if (d.active == RcActiveSource::None) return;
    if (p == &g_p20 && d.active != RcActiveSource::P20_921600) return;
    if (p == &g_p0 && d.active != RcActiveSource::P0_115200) return;

    /* CRSF 模式: 同时输出摇杆帧 + Lua 桥 (老大要求 crsf 既能输出摇杆又能配 Lua)。
     * bridge 下行线程写 UART0 与 out_send 用 g_out_write_mtx 互斥, 防帧交错。 */
    advance_output_latches(d.state);
    out_send(d.state);   // write() outside mutex
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
                                tx_write_uart(outFd, resp, (size_t)rlen);           // 统一走半双工切换入口 (CRSF TX→drain→RX)
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
    std::printf("[dji_rc] bridge 线程启动\n");
    std::fflush(stdout);
    int fd = ::socket(AF_INET, SOCK_DGRAM, 0);
    if (fd < 0) { std::printf("[dji_rc] bridge socket 失败\n"); return; }
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

    std::printf("[dji_rc] crsf-bridge 监听 UDP %s:%d → UART0, bridge_stop=%d\n",
                crsfbr_host, crsfbr_port, g_bridge_stop.load() ? 1 : 0);
    std::fflush(stdout);

    while (!g_bridge_stop.load(std::memory_order_relaxed)) {
        uint8_t pkt[4 + CRSF_FRAME_MAX];
        ssize_t n = ::recvfrom(fd, pkt, sizeof(pkt), 0, NULL, NULL);
        if (n > 0) {
            std::printf("[dji_rc] bridge recv %ldB magic=%02x%02x%02x%02x\n",
                        n, pkt[0], pkt[1], pkt[2], pkt[3]);
            std::fflush(stdout);
            /* 校验 magic "CRSF" + 帧长合法, 原样写 UART0 */
            if (n >= 5 && memcmp(pkt, &CRSFBR_MAGIC, 4) == 0) {
                uint8_t flen = pkt[4 + 1];   /* CRSF len 字段 */
                int ofd = g_out_fd.load();
                std::printf("[dji_rc] bridge fwd: n=%ld flen=%d n-4=%ld g_out_fd=%d\n",
                            n, flen, (long)(n - 4), ofd);
                std::fflush(stdout);
                if (flen + 2 == (uint8_t)(n - 4) && ofd >= 0) {
                    /* Lua 帧入单帧缓冲, 由 out_send 下一拍替代通道帧发送
                       (CRSF 时分复用, EdgeTX 规范) */
                    tx_lua_enqueue(pkt + 4, (size_t)(n - 4));
                }
            }
        } else if (n < 0 && errno != EAGAIN && errno != EINTR) {
            if (g_bridge_stop.load(std::memory_order_relaxed)) break;
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

/* 深度匹配提取 key 对应的嵌套 {...} 对象子串 (含花括号)。
 * 与浅匹配 json.find("{", pos) 不同: 遇到内嵌对象 (如 rc_output 里嵌套 src_cfg)
 * 不会在首个 } 处截断。找不到返回空串。 */
static std::string cfg_json_obj(const std::string &json, const std::string &key) {
    std::string pat = "\"" + key + "\"";
    auto pos = json.find(pat);
    if (pos == std::string::npos) return "";
    pos = json.find(":", pos + pat.size());
    if (pos == std::string::npos) return "";
    pos++;
    while (pos < json.size() && (json[pos] == ' ' || json[pos] == '\t' || json[pos] == '\n')) pos++;
    if (pos >= json.size() || json[pos] != '{') return "";
    int depth = 0;
    for (size_t i = pos; i < json.size(); i++) {
        if (json[i] == '{') depth++;
        else if (json[i] == '}') { depth--; if (depth == 0) return json.substr(pos, i - pos + 1); }
    }
    return "";
}

/* 从 SPI flash config (/dev/mtdblock0 @0xFD000) 读 rc_output 配置。
 * 返回 false 表示无 rc_output 段 (保持命令行默认)。成功则写 mode/baud/sbus_std 并
 * 可能更新 g_ch_map / g_ch_map_valid。 */
static void parse_channel_locks(const std::string &s, bool out[CH_COUNT])
{
    std::memset(out, 0, sizeof(bool) * CH_COUNT);
    size_t pos = 0;
    for (int idx = 0; idx < CH_COUNT; idx++) {
        if (pos >= s.size()) break;
        auto comma = s.find(",", pos);
        std::string tok = s.substr(pos, comma == std::string::npos ? std::string::npos : comma - pos);
        while (!tok.empty() && (tok.front() == ' ' || tok.front() == '\t')) tok.erase(0, 1);
        while (!tok.empty() && (tok.back() == ' ' || tok.back() == '\t')) tok.pop_back();
        out[idx] = (tok == "1" || tok == "true" || tok == "on" || tok == "yes");
        if (comma == std::string::npos) break;
        pos = comma + 1;
    }
}

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

    /* 深度匹配提取整个 rc_output 对象 (内嵌套 src_cfg, 浅匹配首个 } 会停在 src_cfg 闭括号) */
    std::string obj = cfg_json_obj(json, "rc_output");
    if (obj.empty()) return false;

    auto modeS = cfg_json_str(obj, "mode");
    if (modeS == "crsf") { mode = 'c'; found = true; }
    else if (modeS == "sbus") { mode = 's'; found = true; }

    auto stdS = cfg_json_str(obj, "sbus_std");
    if (stdS == "false") sbus_std = false;
    else if (stdS == "true") sbus_std = true;

    auto baudS = cfg_json_str(obj, "baud");
    /* 标准 SBUS: 100k 8E2; 非标准: 115200 8N1; CRSF: 115200 8N1 */
    if (baudS == "auto" || baudS.empty()) {
        if (mode == 'c') baud = 400000;   /* ELRS/MLRS 统一 400k (V3s DLF 输出 401070, +0.27%, STM32 硬件 UART 兼容) */
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
    bool lockCfg[CH_COUNT];
    parse_channel_locks(cfg_json_str(obj, "lock"), lockCfg);
    std::memcpy(g_ch_lock, lockCfg, CH_COUNT);
    {
        std::lock_guard<std::mutex> lock(g_lock_mtx);
        for (int i = 0; i < CH_COUNT; i++) {
            if (!lockCfg[i]) {
                g_lock_state[i] = false;
                g_lock_prev_high[i] = false;
                g_lock_on_value[i] = 0;
                g_lock_off_value[i] = 0;
            }
        }
    }
    /* src_cfg: 每输入源输出值 (缺省保持默认)。持锁调用 rc_map_set_cfg,
     * 与 out_send (rx_thread) 持锁调用 rc_map_build 串行化, 防 g_cfg 撕裂读。 */
    rc_src_cfg_t srcCfg;
    rc_cfg_defaults(&srcCfg);
    std::string sc = cfg_json_obj(obj, "src_cfg");
    if (!sc.empty()) {
        for (int i = 0; i < CFG_COUNT; i++) {
            std::string vs = cfg_json_str(sc, rc_cfg_names[i]);
            if (!vs.empty()) srcCfg.v[i] = (uint16_t)std::atoi(vs.c_str());
        }
        rc_cfg_sanitize(&srcCfg);   /* 钳位非法值, 防 SBUS/CRSF 垃圾脉宽 */
    }
    rc_map_set_cfg(&srcCfg);
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
    bool debug_uart0 = false;                /* --debug-uart0 启用 UART0 调试镜像输出 */
    const char *debug_dev = "/dev/ttyS0";
    int debug_baud = 115200;
    const char *out_dev = "/dev/ttySC0";     /* 协议输出口: 默认 SC16IS752 通道 A */
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
        /* bridge (ELRS Lua 桥) 仅 CRSF 模式启用; SPI 是 sbus 时禁用 bridge,
         * 使 UART0 正常输出 SBUS (而非被 bridge 强制 CRSF)。 */
        if (out_mode == 's') g_crsf_bridge = false;
    }
    g_out_mode.store(out_mode);   // C1: atomic store
    if (out_baud == 0) out_baud = (out_mode == 'c') ? 115200 : (g_sbus_std ? 100000 : 115200);
    g_out_baud.store(out_baud);   /* 先修复零值再赋值 */  // C1: atomic store
    g_crsf_telem = crsf_telem;

    /* bridge 模式: 强制 CRSF 输出 (UART0 双向 CRSF, 参数帧透明转发) */
    if (g_crsf_bridge) {
        out_mode = 'c';
        g_out_mode = 'c';
        g_crsf_telem = true;
        if (out_baud == 0) out_baud = 115200;
        g_out_baud = out_baud;
        std::printf("[dji_rc] crsf-bridge 模式: SC16 UART-A CRSF %d baud, 参数帧转发网口\n", out_baud);
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
    g_out_dev = out_dev;
    bool out_uses_sc16 = out_dev_is_sc16(out_dev);
    std::printf("[dji_rc] protocol output on %s (%s)\n",
                out_dev, out_uses_sc16 ? "SC16/AUX" : "UART0 fallback");
    std::fflush(stdout);

    // TMUX1511 只服务 SC16IS752 共享总线; UART0 fallback 不碰 PB2-PB5。
    if (out_uses_sc16) {
        aux_tmux_apply();
    } else {
        std::printf("[dji_rc] TMUX skipped for UART0 fallback output\n");
        std::fflush(stdout);
    }

    // 协议输出: SBUS 标准=100k 8E2, SBUS 非标=115200 8N1, CRSF=115200/400000 8N1
    bool out_even2 = (out_mode == 's') && g_sbus_std;
    int newFd = uart_open_out(out_dev, out_baud, out_even2);
    g_out_fd.store(newFd);   // C1: atomic store
    if (newFd < 0) {
        std::fprintf(stderr, "[dji_rc] 输出口打开失败: %s @%d\n", out_dev, out_baud);
    } else {
        std::printf("[dji_rc] 输出 %c: %s @%d %s fd=%d (通道映射 %s)\n",
                    out_mode, out_dev, out_baud, out_even2 ? "8E2" : "8N1", newFd,
                    g_ch_map_valid.load() ? "custom" : "default");
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
    std::thread t1, t2, t3, t4, t_app;
    crsf_params_init();   /* 初始化 CRSF 参数表 (Device_Ping 响应用) */
    if (g_p20.fd >= 0) t1 = std::thread(rx_thread, &g_p20);
    if (g_p0.fd  >= 0) t2 = std::thread(rx_thread, &g_p0);
    t_app = std::thread(app_rc_thread);
    /* 上行 crsf_rx_thread: CRSF 遥测回传 或 bridge 模式都需要 (bridge 双向转发 ELRS 响应) */
    if ((out_mode == 'c' && g_crsf_telem) || g_crsf_bridge) {
        if (g_out_fd.load() >= 0)
            t3 = std::thread(crsf_rx_thread);
    }
    if (g_crsf_bridge && g_out_fd >= 0) {
        g_bridge_stop.store(false);
        t4 = std::thread(crsf_bridge_rx_thread);   /* bridge 下行: 网口 → UART0 */
    }

    // 主循环: 状态文件写入 + 控制台打印 (SBUS/CRSF 输出走独立事件驱动)
    std::printf("[dji_rc] Ctrl+C 停止\n\n");
    while (!g_stop.load(std::memory_order_relaxed)) {
        struct timespec ts = {0, interval_ms * 1000000L};
        nanosleep(&ts, nullptr);

        /* Lua 帧由 out_send 限流统一发送 (每 3 周期取 1 帧), 移除兜底:
         * 实测兜底线程的 tx_write_uart 写 Lua 帧 SC16 不输出 (被 out_send 摇杆覆盖),
         * 而 out_send 发 Lua 正常。无 RC 输入时 Lua 参数请求低频, 可接受延迟。 */
        // static int64_t last_lua = 0;
        // int64_t now_lua = now_us();
        // if (now_lua - last_lua >= 15000LL) { ... }

        rc_state_t s20, s0, sapp;
        uint32_t g20, g0, rx20, rx0, appGood, appRx;
        int64_t l20, l0, lapp;

        g_mtx.lock();
        s20 = g_p20.state; g20 = g_p20.good; rx20 = g_p20.rx_bytes; l20 = g_p20.last_us;
        s0  = g_p0.state;  g0  = g_p0.good;  rx0  = g_p0.rx_bytes;  l0  = g_p0.last_us;
        sapp = g_app_rc; appGood = g_app_good; appRx = g_app_rx; lapp = g_app_last_us;
        g_mtx.unlock();

        int64_t n = now_us();
        int64_t age20 = (s20.type == RC_NONE) ? INT64_MAX : n - l20;
        int64_t age0  = (s0.type  == RC_NONE) ? INT64_MAX : n - l0;
        int64_t ageApp = (sapp.type == RC_NONE) ? INT64_MAX : n - lapp;
        bool appFresh = (sapp.type != RC_NONE) && (ageApp <= 80000LL);

        /* 输入源: 串口 (UART1/2 DJI 遥控) 优先; 无串口 → App 融合 (adb getevent + 40007)。
         * 老大定: 有串口用串口, 没串口默认 adb+40007, 输出源头唯一。 */
        RcSourceDecision d = rc_select_priority_source(s20, age20, s0, age0,
                                                       P20_PRIORITY_US, RC_STALE_US);
        rc_state_t m;
        if (d.active != RcActiveSource::None) {
            m = d.state;   /* 串口有数据, 串口优先 */
        } else if (appFresh) {
            m = sapp;      /* 无串口 → App RCM1 融合输入 (adb getevent + 40007) */
        } else {
            m = d.state;
        }

        if (m.type != RC_NONE) {
            // 推进 latch (L1~R3 互斥自锁 + 通道锁): 串口路径由 handle_pkt 推进, App 融合路径无事件驱动,
            // 必须由主循环定时推进, 否则 update_lr_latch 永不执行 → lr_pos 恒 0。
            advance_output_latches(m);
            // 状态文件 (供 web_server /api/rc)
            const char *activeSrc = appFresh ? "android_rcm1" : rc_active_source_name(d.active);
            write_state_file(m, activeSrc, g20, g0, rx20, rx0,
                             appGood, appRx, ageApp, appFresh, now_us());
            send_rcmsg(rcmsg_fd, rcmsg_dst, m, true, ++rcmsg_seq, n);
        } else if (rx20 > 0 || rx0 > 0) {
            // UART有数据但RC掉线: 写空状态防旧数据残留
            static const char no_rc[] = "{\"error\":\"no RC data\",\"rx1\":%u,\"rx2\":%u}\n";
            char buf[128];
            int w = snprintf(buf, sizeof(buf), no_rc, rx20, rx0);
            write_text_atomic("/tmp/rc_state.json", buf, w);
            write_text_atomic("/var/log/rc_state.json", buf, w);
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
        // bridge 模式: load_rc_output_cfg 仍会更新 src_cfg/map/lock (反向/范围/映射即时生效),
        // 但跳过 mode/baud 变化导致的 UART0 角色重开 (保持 CRSF bridge 波特率/转发不受干扰)。
        static int64_t last_cfg_check = 0;
        if (n - last_cfg_check > 2000000LL) {
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
            /* 按 SPI 配置热重配: bridge (ELRS Lua 桥) 状态随 mode 切换。
             * crsf → 启用 bridge (Lua 桥可用); sbus → 停 bridge (UART0 正常 SBUS 输出)。 */
            bool modeDiff = (cm != g_out_mode.load() || cb != g_out_baud.load() || cs != g_sbus_std);
            bool reconfigureIo = cfgOk && modeDiff;
            if (reconfigureIo) {
                std::printf("[dji_rc] 输出配置变化 mode=%c baud=%d sbus_std=%d → 热重配\n",
                            cm, cb, cs ? 1 : 0);
                std::fflush(stdout);
                bool oldCrsf = (g_out_mode.load() == 'c');
                g_out_mode.store(cm); g_out_baud.store(cb); g_sbus_std = cs;   // C1: atomic store
                /* bridge (ELRS Lua 桥) 随 SPI mode 启停: crsf→启用, sbus→停用 */
                g_crsf_bridge = (cm == 'c');
                /* TMUX1511 模式随输出模式切换 (SBUS / CRSF 半双工), 仅 SC16 输出需要。 */
                if (out_uses_sc16) {
                    aux_tmux_apply();
                }

                /* 先安全停掉旧回传线程 (CRSF->任何 或 任何->CRSF 切换) */
                if (t3.joinable()) {
                    g_crsf_stop.store(true);
                    /* 关闭 fd 使阻塞的 read 立即返回 */
                    int oldFd = g_out_fd.exchange(-1);   // C1: atomic
                    if (oldFd >= 0) { ::close(oldFd); }
                    t3.join();
                    g_crsf_stop.store(false);
                }
                /* 切到 sbus 时停掉 bridge 下行线程 (UART0 不再做 Lua 转发) */
                if (cm == 's' && t4.joinable()) {
                    g_bridge_stop.store(true);
                    int oldFd = g_out_fd.exchange(-1);   // C1: atomic
                    if (oldFd >= 0) { ::close(oldFd); }
                    t4.join();
                    g_bridge_stop.store(false);
                }
                /* 重开输出 fd (无条件): 确保波特率/校验更新。
                 * 若 t3/t4 未 joinable (SBUS 无回传线程) 旧 fd 不会自动关闭,
                 * 直接关旧 fd 再重开, 否则 g_out_fd>=0 跳过重开 → 波特率不变。 */
                bool even2 = (g_out_mode.load() == 's') && g_sbus_std;
                int oldOutFd = g_out_fd.exchange(-1);   // C1: atomic 取走旧 fd
                if (oldOutFd >= 0) { ::close(oldOutFd); }
                g_out_fd.store(uart_open_out(out_dev, g_out_baud.load(), even2));   // C1: atomic
                if (g_out_fd.load() < 0)
                    std::fprintf(stderr, "[dji_rc] 热重配输出打开失败\n");

                /* CRSF 模式启动回传线程 */
                if (g_out_mode.load() == 'c' && g_crsf_telem && g_out_fd.load() >= 0 && !t3.joinable()) {
                    g_crsf_stop.store(false);
                    t3 = std::thread(crsf_rx_thread);
                }
                /* CRSF 模式启动 bridge 下行线程 (ELRS Lua 桥) */
                if (g_crsf_bridge && g_out_fd.load() >= 0 && !t4.joinable()) {
                    g_bridge_stop.store(false);
                    t4 = std::thread(crsf_bridge_rx_thread);
                }
                (void)oldCrsf;
            }
        }

        // 控制台状态日志限频: stdout 由 S99 管道收集，50Hz 打印会反压卡住主循环。
        static int64_t last_status_log_us = 0;
        if (n - last_status_log_us >= 1000000LL) {
            last_status_log_us = n;
            char line[256];
            line[0] = '\0';
            if (m.type == RC_NONE) {
                snprintf(line, sizeof(line), "no-RC rx1=%u rx2=%u", rx20, rx0);
            } else {
                rc_state_to_kv(&m, line, sizeof(line));
            }
            std::printf("[dji_rc] %s | g1=%u g2=%u app=%u primary=%s rx1=%u rx2=%u app_rx=%u\n",
                        line, g20, g0, appGood, appFresh ? "app" : "uart", rx20, rx0, appRx);
            if (debug_uart0 && (n - g_last_debug_us) >= 5000000LL) {
                debug_log("[dji_rc][dbg] %s g1=%u g2=%u rx1=%u rx2=%u age1=%lld age2=%lld",
                          line, g20, g0, rx20, rx0, (long long)age20, (long long)age0);
                g_last_debug_us = n;
            }
        }
    }

    g_stop.store(true);
    g_crsf_stop.store(true);
    g_bridge_stop.store(true);   /* 停 bridge 下行线程 */
    /* 先关闭 fd 唤醒阻塞的 read, 再 join, 避免死锁 */
    if (g_p20.fd >= 0) { ::close(g_p20.fd); g_p20.fd = -1; }
    if (g_p0.fd  >= 0) { ::close(g_p0.fd);  g_p0.fd  = -1; }
    int outFdClean = g_out_fd.exchange(-1);   // C1: atomic
    if (outFdClean >= 0) { ::close(outFdClean); }
    if (g_debug_fd >= 0) ::close(g_debug_fd);
    if (t3.joinable()) t3.join();
    if (t4.joinable()) t4.join();   /* bridge 下行线程 */
    if (t_app.joinable()) t_app.join();
    if (t1.joinable()) t1.join();
    if (t2.joinable()) t2.join();
    if (rcmsg_fd >= 0) ::close(rcmsg_fd);
    if (tlm_fd >= 0) ::close(tlm_fd);
    return 0;
}
