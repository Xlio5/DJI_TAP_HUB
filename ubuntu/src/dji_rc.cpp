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

#include <fcntl.h>
#include <termios.h>
#include <unistd.h>

extern "C" {
#include "duml.h"
#include "rc_decode.h"
#include "chmap.h"
#include "sbus.h"
}

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
static int g_debug_fd = -1;
static int64_t g_last_debug_us = 0;
static int g_sbus_fd = -1;

static void debug_log(const char *fmt, ...);

// ═══════════════════════════════════════════════════════════════════════
// helpers
// ═══════════════════════════════════════════════════════════════════════

static int64_t now_us() {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (int64_t)ts.tv_sec * 1000000 + ts.tv_nsec / 1000;
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

// ── SBUS 输出: P20 每解一帧就立刻发 ──────────────────────────────

static void sbus_send_if_p20(DjiPort *p)
{
    static uint32_t sbus_attempts = 0;
    static uint32_t sbus_errors = 0;

    if (p != &g_p20) return;
    if (g_p20.state.type == RC_NONE) return;

    int64_t n = now_us();
    if ((n - g_p20.last_us) > 500000LL) return;
    if (g_sbus_fd < 0) return;

    int64_t age20 = n - g_p20.last_us;
    int64_t age0  = (g_p0.state.type == RC_NONE) ? INT64_MAX : n - g_p0.last_us;

    rc_state_t m;
    rc_merge(&g_p20.state, age20, &g_p0.state, age0, 500000LL, &m);

    if (m.type != RC_NONE) {
        uint16_t ch[CH_COUNT];
        chmap_build(&m, ch);
        uint8_t frame[SBUS_FRAME_LEN];
        sbus_encode(ch, frame);
        // write() outside mutex — caller must NOT hold g_mtx
        ssize_t written = ::write(g_sbus_fd, frame, SBUS_FRAME_LEN);
        sbus_attempts++;
        if (written != SBUS_FRAME_LEN) {
            sbus_errors++;
            std::printf("[dji_rc] sbus write fail written=%d errno=%d attempts=%u errors=%u\n",
                        (int)written, errno, sbus_attempts, sbus_errors);
            debug_log("[dji_rc][dbg] sbus write fail written=%d errno=%d attempts=%u errors=%u",
                      (int)written, errno, sbus_attempts, sbus_errors);
        } else if (sbus_attempts <= 10 || (sbus_attempts % 50) == 0) {
            std::printf("[dji_rc] sbus write ok attempts=%u ch1=%u ch2=%u ch3=%u ch4=%u\n",
                        sbus_attempts, ch[0], ch[1], ch[2], ch[3]);
            debug_log("[dji_rc][dbg] sbus write ok attempts=%u ch1=%u ch2=%u ch3=%u ch4=%u",
                      sbus_attempts, ch[0], ch[1], ch[2], ch[3]);
        }
    }
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
    const char *sbus_dev = "/dev/ttyS2";
    int sbus_baud = 115200;

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
        else if (std::strcmp(argv[i], "--sbus-out") == 0 && i + 1 < argc) sbus_dev = argv[++i];
        else if (std::strcmp(argv[i], "--sbus-baud") == 0 && i + 1 < argc) sbus_baud = std::atoi(argv[++i]);
        else if (std::strcmp(argv[i], "--selftest") == 0) { selftest(); return 0; }
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
    g_sbus_fd = uart_open(sbus_dev, sbus_baud);
    if (g_sbus_fd < 0) {
        std::fprintf(stderr, "[dji_rc] SBUS output open failed: %s @%d\n", sbus_dev, sbus_baud);
    } else {
        std::printf("[dji_rc] SBUS output: %s @%d fd=%d\n", sbus_dev, sbus_baud, g_sbus_fd);
        debug_log("[dji_rc][dbg] sbus output %s @%d fd=%d", sbus_dev, sbus_baud, g_sbus_fd);
    }

    // 启动接收线程 (SBUS 在 P20 rx_thread 的 handle_pkt 里事件驱动发送)
    std::thread t1, t2;
    if (g_p20.fd >= 0) t1 = std::thread(rx_thread, &g_p20);
    if (g_p0.fd  >= 0) t2 = std::thread(rx_thread, &g_p0);

    // 主循环: 状态文件写入 + 控制台打印 (100ms, SBUS 走独立线程)
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
    if (t1.joinable()) t1.join();
    if (t2.joinable()) t2.join();
    if (g_p20.fd >= 0) ::close(g_p20.fd);
    if (g_p0.fd  >= 0) ::close(g_p0.fd);
    if (g_debug_fd >= 0) ::close(g_debug_fd);
    if (g_sbus_fd >= 0) ::close(g_sbus_fd);
    return 0;
}
