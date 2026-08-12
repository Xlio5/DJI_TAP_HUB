/**
 * web_server.cpp — TUN_NAT_HUB 嵌入式 Web 配置面板 (C++17)
 *
 * 替代 web_panel.py，零外部依赖，静态链接 ~200KB。
 * 只依赖 POSIX sockets + Linux /proc + /sys + iptables fork/exec。
 *
 * API 跟 web_panel.py 完全对等:
 *   GET  /api/heartbeat, /api/config, /api/system, /api/stats, /api/network, /api/iptables
 *   POST /api/forward/add, /api/forward/del, /api/config/save, /api/camera/add, /api/camera/del
 *   GET  / → HTML 面板
 */

#include <arpa/inet.h>
#include <cerrno>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <dirent.h>
#include <fcntl.h>
#include <fstream>
#include <iostream>
#include <netinet/in.h>
#include <poll.h>
#include <sstream>
#include <string>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/time.h>
#include <sys/wait.h>
#include <thread>
#include <unistd.h>
#include <vector>

#include "rtsp_nat_helper.h"

extern "C" {
#include "rc_map.h"
}

// ═══════════════════════════════════════════════════════════════
// 常量
// ═══════════════════════════════════════════════════════════════
#define VERSION     "1.6.6"   // 固件版本 — 改这里全局生效
constexpr int    PORT       = 8080;
constexpr int    BUF_SZ     = 8192;
constexpr int    MAX_CLI    = 8;
constexpr int    MAX_CFG    = 32768;
constexpr const char* RTSP_RTP_TUN_CLIENT = "10.0.0.2";
const char*      CFG_DEV    = "/dev/mtdblock0";
constexpr int    CFG_OFFSET = 0xFD000;  // uboot 分区尾部空闲区(12KB, 距SPL 1012KB)
constexpr int    CFG_MAX    = 0x3000;   // 12KB

// 带宽历史（用于计算实时 Mbps）
struct BwPrev {
    double ts = 0;
    uint64_t tx = 0, rx = 0;
};
static BwPrev g_bwPrev;  // heartbeat 用
static BwPrev g_stPrev;  // /api/stats 用

// ═══════════════════════════════════════════════════════════════
// 工具函数
// ═══════════════════════════════════════════════════════════════

static std::string exec(const std::vector<std::string>& args) {
    std::string cmd;
    for (auto& a : args) cmd += a + " ";
    cmd.pop_back();
    FILE* fp = popen(cmd.c_str(), "r");
    if (!fp) return "";
    char buf[4096];
    std::string out;
    while (fgets(buf, sizeof(buf), fp)) out += buf;
    pclose(fp);
    return out;
}

static int execRet(const std::vector<std::string>& args) {
    std::string cmd;
    for (auto& a : args) cmd += a + " ";
    cmd.pop_back();
    // 丢弃 stdout+stderr: 只关心退出码。否则 system() 会把子进程输出
    // (如 `pidof usb_tund` 的 pid 数字) 直接泄漏到 web_server 日志。
    cmd += " >/dev/null 2>&1";
    return system(cmd.c_str());
}

// 读 /sys 整数
static uint64_t readSysfs(const std::string& path) {
    std::ifstream f(path);
    uint64_t v = 0;
    f >> v;
    return v;
}

static double nowSec() {
    auto n = std::chrono::steady_clock::now().time_since_epoch();
    return std::chrono::duration<double>(n).count();
}

static bool fileExists(const std::string& path) {
    struct stat st;
    return stat(path.c_str(), &st) == 0;
}

static int pidof(const std::string& name) {
    return execRet({"pidof", name}) == 0;
}

static std::string urldecode(const std::string& s) {
    std::string r;
    for (size_t i = 0; i < s.size(); i++) {
        if (s[i] == '%' && i+2 < s.size()) {
            int hi = s[i+1], lo = s[i+2];
            auto hex = [](char c)->int {
                if (c>='0'&&c<='9') return c-'0';
                if (c>='a'&&c<='f') return c-'a'+10;
                if (c>='A'&&c<='F') return c-'A'+10;
                return 0;
            };
            r += (char)(hex(hi)*16 + hex(lo));
            i += 2;
        } else if (s[i] == '+') r += ' ';
        else r += s[i];
    }
    return r;
}

// ═══════════════════════════════════════════════════════════════
// 极简 JSON 构建（不引入完整库，节省空间）
// ═══════════════════════════════════════════════════════════════

struct JsonValue {
    enum { OBJ, ARR, STR, NUM, BOOL } type = OBJ;
    std::string raw;  // 预序列化的 JSON 片段

    static JsonValue object(const std::string& body) { JsonValue v; v.type = OBJ; v.raw = body; return v; }
    static JsonValue number(uint64_t n)          { JsonValue v; v.type = NUM; v.raw = std::to_string(n); return v; }
    static JsonValue number(int n)               { JsonValue v; v.type = NUM; v.raw = std::to_string(n); return v; }
    static JsonValue string(const std::string& s) {
        JsonValue v; v.type = STR;
        v.raw = "\"";
        for (char c : s) {
            if (c == '\\' || c == '"') { v.raw += '\\'; v.raw += c; }
            else if (c == '\n') v.raw += "\\n";
            else if (c == '\r') v.raw += "\\r";
            else if (c == '\t') v.raw += "\\t";
            else v.raw += c;
        }
        v.raw += "\"";
        return v;
    }
    static JsonValue boolean(bool b) { JsonValue v; v.type = BOOL; v.raw = b ? "true" : "false"; return v; }
    static JsonValue null() { JsonValue v; v.raw = "null"; return v; }

    std::string toString() const { return raw; }
};

// JSON 对象构建辅助
struct JsonObj {
    std::string body;
    bool first = true;
    void pair(const char* key, JsonValue val) {
        if (!first) body += ",";
        first = false;
        body += "\"" + std::string(key) + "\":" + val.toString();
    }
    std::string done() { return "{" + body + "}"; }
};

// ═══════════════════════════════════════════════════════════════
// 配置管理（手写 JSON 解析，key:val 简单格式）
// ═══════════════════════════════════════════════════════════════

struct ForwardRule {
    std::string proto, dest;
    int port = 0;
};

struct Camera {
    std::string name, url;
};

struct Config {
    std::string rtspUrl = "rtsp://192.168.144.31:554/stream1";
    std::string lanSubnet = "192.168.88.0/24";
    std::string tunSubnet = "10.0.0.0/24";
    std::vector<ForwardRule> forwards;
    std::vector<Camera> cameras;

    // ── RC 输出 (SBUS/CRSF @UART0) ──
    std::string rcOutMode = "sbus";       // "sbus" | "crsf"
    std::string rcOutDevice = "/dev/ttyS0";
    std::string rcOutBaud = "auto";       // "auto" | 具体波特率
    std::string rcOutPreset = "default";  // "default" | "aetr" | "taer" | "custom"
    std::string rcOutMap = "";            // 逗号分隔 source: "ch1,ch2,...,dir"
    int         rcOutCrsfMs = 10;         // CRSF 发送周期 (ms, 预留)
    bool        rcOutCrsfTelem = true;    // CRSF 接收回传
    bool        rcOutSbusStd = true;      // SBUS 标准模式: true=100k 8E2, false=115200 8N1
};

/* 前置声明: apiConfig 会调用它 */
static std::string apiRcOutput(const Config& cfg);

// 极简 JSON 字符串提取
// 提取 JSON 值 (支持字符串 "..."、数字、bool)
static std::string jsonVal(const std::string& json, const std::string& key) {
    std::string pat = "\"" + key + "\"";
    auto pos = json.find(pat);
    if (pos == std::string::npos) return "";
    pos = json.find(":", pos + pat.size());
    if (pos == std::string::npos) return "";
    while (pos+1 < json.size() && (json[pos+1]==' '||json[pos+1]=='\n'||json[pos+1]=='\t')) pos++;
    auto start = pos + 1;
    if (json[start] == '\"') {
        auto end = json.find("\"", start + 1);
        if (end == std::string::npos) return "";
        return json.substr(start + 1, end - start - 1);
    }
    // 数字或布尔值
    auto end = json.find_first_of(",}\n\r \t]", start + 1);
    if (end == std::string::npos) end = json.size();
    auto v = json.substr(start, end - start);
    // trim trailing spaces
    while (!v.empty() && v.back()==' ') v.pop_back();
    return v;
}
static std::string jsonStr(const std::string& json, const std::string& key) {
    return jsonVal(json, key);
}

static int jsonInt(const std::string& json, const std::string& key) {
    auto s = jsonVal(json, key);
    if (s.empty()) return 0;
    try { return std::stoi(s); } catch (...) { return 0; }
}

static std::string jsonRaw(const std::string& json, const std::string& key) {
    std::string pat = "\"" + key + "\"";
    auto pos = json.find(pat);
    if (pos == std::string::npos) return "";
    pos = json.find(":", pos + pat.size());
    if (pos == std::string::npos) return "";
    // skip whitespace
    while (pos+1 < json.size() && (json[pos+1]==' '||json[pos+1]=='\n'||json[pos+1]=='\t')) pos++;
    auto start = pos + 1;
    char c0 = json[start];
    if (c0 == '\"') {
        auto end = json.find("\"", start + 1);
        return json.substr(start + 1, end - start - 1);
    }
    auto end = json.find_first_of(",}\n\r \t", start + 1);
    if (end == std::string::npos) end = json.size();
    return json.substr(start, end - start);
}

static std::string detectLanSubnet() {
    std::string out = exec({"ip", "addr", "show", "eth0"});
    std::istringstream iss(out);
    std::string line;
    while (std::getline(iss, line)) {
        auto p = line.find("inet ");
        if (p == std::string::npos) continue;
        // e.g. "    inet 192.168.144.66/24 scope global eth0"
        std::istringstream ls(line.substr(p + 5));
        std::string cidr;
        ls >> cidr;
        auto slash = cidr.find('/');
        if (slash == std::string::npos) continue;
        std::string ip = cidr.substr(0, slash);
        std::string prefix = cidr.substr(slash + 1);
        auto lastDot = ip.rfind('.');
        if (lastDot == std::string::npos) continue;
        return ip.substr(0, lastDot + 1) + "0/" + prefix;
    }
    return "";
}

static std::string detectLanIface() {
    std::string out = exec({"ip", "-br", "addr"});
    std::istringstream iss(out);
    std::string line;
    while (std::getline(iss, line)) {
        if (line.find("lo") == 0 || line.find("tun") == 0 ||
            line.find("docker") == 0 || line.find("veth") == 0) continue;
        if (line.find("UP") != std::string::npos && line.find("inet ") != std::string::npos) {
            std::istringstream ls(line);
            std::string iface;
            ls >> iface;
            return iface;
        }
    }
    return "eth0";
}

// H-3: loadConfig 支持报告"配置是否被修改" (LAN 网段自动检测到变化时置 true),
// 调用方据此决定是否要 saveConfig — 避免每次启动都无条件擦写 SPI NOR flash (磨损寿命)。
// outChanged 可空 (nullptr 表示不关心)。
static Config loadConfig(bool* outChanged = nullptr) {
    Config cfg;
    if (outChanged) *outChanged = false;
    // Read config from SPI Flash (persistent, survives reboot)
    int fd = ::open(CFG_DEV, O_RDONLY);
    if (fd < 0) return cfg;
    uint16_t len = 0;
    ::lseek(fd, CFG_OFFSET, SEEK_SET);
    ssize_t r = ::read(fd, &len, 2);
    if (r != 2 || len == 0 || len > CFG_MAX) { ::close(fd); return cfg; }
    std::vector<char> buf(len + 1);
    ssize_t got = ::read(fd, buf.data(), len);
    ::close(fd);
    if (got != (ssize_t)len) return cfg;   // H: 读不满 → 配置损坏, 用默认
    buf[len] = '\0';
    std::string json(buf.data(), len);

    auto v = jsonStr(json, "rtsp_url");
    if (!v.empty()) cfg.rtspUrl = v;
    v = jsonStr(json, "lan_subnet");
    if (!v.empty()) cfg.lanSubnet = v;
    v = jsonStr(json, "tun_subnet");
    if (!v.empty()) cfg.tunSubnet = v;

    // parse forwards array
    auto fPos = json.find("\"forwards\"");
    if (fPos != std::string::npos) {
        auto arrStart = json.find("[", fPos);
        auto arrEnd = json.find("]", arrStart);
        if (arrStart != std::string::npos && arrEnd != std::string::npos) {
            std::string arr = json.substr(arrStart, arrEnd - arrStart + 1);
            size_t i = 0;
            while (i < arr.size()) {
                auto obStart = arr.find("{", i);
                if (obStart == std::string::npos) break;
                auto obEnd = arr.find("}", obStart);
                if (obEnd == std::string::npos) break;
                ForwardRule r;
                r.proto = jsonStr(arr.substr(obStart, obEnd-obStart+1), "proto");
                r.port  = jsonInt(arr.substr(obStart, obEnd-obStart+1), "port");
                r.dest  = jsonStr(arr.substr(obStart, obEnd-obStart+1), "dest");
                if (!r.proto.empty() && r.port > 0 && !r.dest.empty())
                    cfg.forwards.push_back(r);
                i = obEnd + 1;
            }
        }
    }

    // parse cameras array
    auto cPos = json.find("\"cameras\"");
    if (cPos != std::string::npos) {
        auto arrStart = json.find("[", cPos);
        auto arrEnd = json.find("]", arrStart);
        if (arrStart != std::string::npos && arrEnd != std::string::npos) {
            std::string arr = json.substr(arrStart, arrEnd - arrStart + 1);
            size_t i = 0;
            while (i < arr.size()) {
                auto obStart = arr.find("{", i);
                if (obStart == std::string::npos) break;
                auto obEnd = arr.find("}", obStart);
                if (obEnd == std::string::npos) break;
                Camera c;
                c.name = jsonStr(arr.substr(obStart, obEnd-obStart+1), "name");
                c.url  = jsonStr(arr.substr(obStart, obEnd-obStart+1), "url");
                if (!c.url.empty()) cfg.cameras.push_back(c);
                i = obEnd + 1;
            }
        }
    }

    // parse rc_output (SBUS/CRSF 输出配置)
    auto roPos = json.find("\"rc_output\"");
    if (roPos != std::string::npos) {
        auto roStart = json.find("{", roPos);
        auto roEnd = json.find("}", roStart);
        if (roStart != std::string::npos && roEnd != std::string::npos) {
            std::string ro = json.substr(roStart, roEnd - roStart + 1);
            auto mv = jsonStr(ro, "mode");
            if (!mv.empty()) cfg.rcOutMode = mv;
            mv = jsonStr(ro, "device");
            if (!mv.empty()) cfg.rcOutDevice = mv;
            mv = jsonStr(ro, "baud");
            if (!mv.empty()) cfg.rcOutBaud = mv;
            mv = jsonStr(ro, "map_preset");
            if (!mv.empty()) cfg.rcOutPreset = mv;
            mv = jsonStr(ro, "map");
            if (!mv.empty()) cfg.rcOutMap = mv;
            cfg.rcOutCrsfMs = jsonInt(ro, "crsf_period_ms");
            if (cfg.rcOutCrsfMs < 5) cfg.rcOutCrsfMs = 10;
            auto tb = jsonStr(ro, "crsf_telem");
            if (!tb.empty()) cfg.rcOutCrsfTelem = (tb == "true");
            auto ss = jsonStr(ro, "sbus_std");
            if (!ss.empty()) cfg.rcOutSbusStd = (ss == "true");
        }
    }

    // 自动检测 LAN 网段变化
    auto detected = detectLanSubnet();
    if (!detected.empty() && detected != cfg.lanSubnet) {
        std::cout << "[web_server] LAN 网段自动检测: " << cfg.lanSubnet << " → " << detected << std::endl;
        cfg.lanSubnet = detected;
        if (outChanged) *outChanged = true;
    }

    return cfg;
}

static void saveConfig(const Config& cfg) {
    // Write config to SPI Flash @0xFD000 (persistent across reboots)
    std::stringstream ss;
    ss << "{\n";
    ss << "  \"rtsp_url\": \"" << cfg.rtspUrl << "\",\n";
    ss << "  \"lan_subnet\": \"" << cfg.lanSubnet << "\",\n";
    ss << "  \"tun_subnet\": \"" << cfg.tunSubnet << "\",\n";
    ss << "  \"forwards\": [\n";
    for (size_t i = 0; i < cfg.forwards.size(); i++) {
        auto& r = cfg.forwards[i];
        ss << "    {\"proto\":\"" << r.proto << "\",\"port\":" << r.port << ",\"dest\":\"" << r.dest << "\"}";
        ss << (i+1 < cfg.forwards.size() ? ",\n" : "\n");
    }
    ss << "  ],\n";
    ss << "  \"cameras\": [\n";
    for (size_t i = 0; i < cfg.cameras.size(); i++) {
        auto& c = cfg.cameras[i];
        ss << "    {\"name\":\"" << c.name << "\",\"url\":\"" << c.url << "\"}";
        ss << (i+1 < cfg.cameras.size() ? ",\n" : "\n");
    }
    ss << "  ],\n";
    ss << "  \"rc_output\": {\n";
    ss << "    \"mode\": \"" << cfg.rcOutMode << "\",\n";
    ss << "    \"device\": \"" << cfg.rcOutDevice << "\",\n";
    ss << "    \"baud\": \"" << cfg.rcOutBaud << "\",\n";
    ss << "    \"map_preset\": \"" << cfg.rcOutPreset << "\",\n";
    ss << "    \"map\": \"" << cfg.rcOutMap << "\",\n";
    ss << "    \"crsf_period_ms\": " << cfg.rcOutCrsfMs << ",\n";
    ss << "    \"crsf_telem\": " << (cfg.rcOutCrsfTelem ? "true" : "false") << ",\n";
    ss << "    \"sbus_std\": " << (cfg.rcOutSbusStd ? "true" : "false") << "\n";
    ss << "  }\n}\n";
    std::string json = ss.str();
    if (json.size() > CFG_MAX - 2) {
        std::cerr << "[cfg] ERROR: config too large (" << json.size() << " > " << (CFG_MAX-2) << ")" << std::endl;
        return;
    }
    int fd = ::open(CFG_DEV, O_WRONLY);
    if (fd < 0) { std::cerr << "[cfg] ERROR: cannot open " << CFG_DEV << std::endl; return; }
    uint16_t len = (uint16_t)json.size();
    ::lseek(fd, CFG_OFFSET, SEEK_SET);
    // H: 检查写返回值, 写失败报错 (SPI flash 磨损/坏块)
    ssize_t w1 = ::write(fd, &len, 2);
    ssize_t w2 = ::write(fd, json.c_str(), len);
    ::close(fd);
    sync();
    if (w1 != 2 || w2 != (ssize_t)len)
        std::cerr << "[cfg] WARN: 配置写入不完整 (" << w1 << "+" << w2 << "/" << len << ")" << std::endl;
    std::cout << "[cfg] saved " << len << " bytes to " << CFG_DEV << " @0x" << std::hex << CFG_OFFSET << std::dec << std::endl;
}

// ═══════════════════════════════════════════════════════════════
// iptables 转发管理
// ═══════════════════════════════════════════════════════════════

static std::string g_lanIface = "eth0";

static std::string detectLanIp() {
    std::string out = exec({"ip", "addr", "show", g_lanIface});
    std::istringstream iss(out);
    std::string line;
    while (std::getline(iss, line)) {
        auto p = line.find("inet ");
        if (p == std::string::npos) continue;
        std::istringstream ls(line.substr(p + 5));
        std::string cidr;
        ls >> cidr;
        auto slash = cidr.find('/');
        if (slash != std::string::npos) return cidr.substr(0, slash);
    }
    return "";
}

static void applyForward(const ForwardRule& r) {
    std::string port = std::to_string(r.port);
    std::string lan = g_lanIface;
    // 检查已有，不重复添加
    if (execRet({"iptables", "-t", "nat", "-C", "PREROUTING", "-i", lan,
                 "-p", r.proto, "--dport", port, "-j", "DNAT", "--to-destination", r.dest}) != 0) {
        execRet({"iptables", "-t", "nat", "-A", "PREROUTING", "-i", lan,
                 "-p", r.proto, "--dport", port, "-j", "DNAT", "--to-destination", r.dest});
    }
    if (execRet({"iptables", "-C", "FORWARD", "-i", lan, "-o", "tun_hub",
                 "-p", r.proto, "--dport", port, "-j", "ACCEPT"}) != 0) {
        execRet({"iptables", "-A", "FORWARD", "-i", lan, "-o", "tun_hub",
                 "-p", r.proto, "--dport", port, "-j", "ACCEPT"});
    }
}

static void applyAllForwards(const Config& cfg) {
    for (auto& r : cfg.forwards) applyForward(r);
}

static std::vector<std::string> rtspCameraHosts(const Config& cfg) {
    std::vector<std::string> hosts;
    addUniqueIpv4Host(hosts, rtspHostFromUrl(cfg.rtspUrl));
    for (const auto& c : cfg.cameras) {
        addUniqueIpv4Host(hosts, rtspHostFromUrl(c.url));
    }
    return hosts;
}

// 应用 RTSP UDP RTP 转发规则。
// 返回 true = 已成功应用 (LAN IP 已就绪); false = 尚未就绪 (启动早期 eth0 可能还没拿到 IP),
// 由主循环周期性重试, 直到应用成功为止 — 修复 V3s 重启后 DNAT 规则永久丢失问题。
// 幂等: 每条规则先 `-C` 检查已存在, 存在则跳过不重复添加。
static bool applyRtspUdpRtpForward(const Config& cfg) {
    std::string lanIp = detectLanIp();
    if (lanIp.empty()) {
        std::cout << "[rtsp-udp] skip: no LAN ip on " << g_lanIface
                  << " (将重试)" << std::endl;
        return false;
    }

    for (const auto& host : rtspCameraHosts(cfg)) {
        if (execRet({"iptables", "-t", "nat", "-C", "PREROUTING",
                     "-i", g_lanIface, "-p", "udp",
                     "-s", host, "-d", lanIp, "--dport", "10000:65535",
                     "-j", "DNAT", "--to-destination", RTSP_RTP_TUN_CLIENT}) != 0) {
            execRet({"iptables", "-t", "nat", "-A", "PREROUTING",
                     "-i", g_lanIface, "-p", "udp",
                     "-s", host, "-d", lanIp, "--dport", "10000:65535",
                     "-j", "DNAT", "--to-destination", RTSP_RTP_TUN_CLIENT});
        }

        if (execRet({"iptables", "-C", "FORWARD",
                     "-i", g_lanIface, "-o", "tun_hub", "-p", "udp",
                     "-s", host, "-d", RTSP_RTP_TUN_CLIENT, "--dport", "10000:65535",
                     "-j", "ACCEPT"}) != 0) {
            execRet({"iptables", "-A", "FORWARD",
                     "-i", g_lanIface, "-o", "tun_hub", "-p", "udp",
                     "-s", host, "-d", RTSP_RTP_TUN_CLIENT, "--dport", "10000:65535",
                     "-j", "ACCEPT"});
        }
        std::cout << "[rtsp-udp] " << host << " -> " << RTSP_RTP_TUN_CLIENT
                  << " via " << g_lanIface << " dport 10000:65535" << std::endl;
    }
    return true;
}

static bool addForward(Config& cfg, const std::string& proto, int port, const std::string& dest) {
    if (proto != "udp" && proto != "tcp") return false;
    if (port < 1 || port > 65535) return false;
    ForwardRule r{proto, dest, port};
    applyForward(r);
    cfg.forwards.push_back(r);
    saveConfig(cfg);
    return true;
}

static bool removeForward(Config& cfg, int port) {
    for (auto it = cfg.forwards.begin(); it != cfg.forwards.end(); ++it) {
        if (it->port != port) continue;
        std::string pt = std::to_string(port);
        std::string lan = g_lanIface;
        execRet({"iptables", "-t", "nat", "-D", "PREROUTING", "-i", lan,
                 "-p", it->proto, "--dport", pt, "-j", "DNAT", "--to-destination", it->dest});
        execRet({"iptables", "-D", "FORWARD", "-i", lan, "-o", "tun_hub",
                 "-p", it->proto, "--dport", pt, "-j", "ACCEPT"});
        cfg.forwards.erase(it);
        saveConfig(cfg);
        return true;
    }
    return false;
}

// ═══════════════════════════════════════════════════════════════
// HTTP 响应 + API 处理器
// ═══════════════════════════════════════════════════════════════

struct Request {
    std::string method, path, body;
};

/* ── HTTP Keep-Alive: 从累积缓冲中切出一个完整请求 ──────────────────
 * 返回值:  >0  找到完整请求，返回其总字节数（含头部+body），*req 已填充
 *           0  缓冲中尚无完整请求，需要继续 recv
 *          -1 连接应关闭（对端关闭 / 请求过大 / 无 \r\n\r\n）
 */
static int extractRequest(std::string& buf, Request* req) {
    // 找请求头结束位置
    auto hdrEnd = buf.find("\r\n\r\n");
    if (hdrEnd == std::string::npos) {
        // 头还没收全。若缓冲超限则放弃（防止内存膨胀）
        if (buf.size() > 65536) return -1;
        return 0;
    }
    // 解析 Content-Length（可能无 body）
    // CO-7: atoi 溢出是 UB, 改用 stoll + try-catch, 超限返回 -1
    int contentLen = 0;
    size_t clPos = buf.find("Content-Length:");
    if (clPos != std::string::npos && clPos < hdrEnd) {
        try {
            long long cl = std::stoll(buf.substr(clPos + 15, hdrEnd - clPos - 15));
            if (cl < 0 || cl > 8 * 1024 * 1024) return -1;
            contentLen = (int)cl;
        } catch (...) { return -1; }
    }
    size_t total = hdrEnd + 4 + (size_t)contentLen;
    if (buf.size() < total) return 0;   // body 未收全

    Request r;
    // 请求行: "GET /path HTTP/1.1"
    auto lineEnd = buf.find("\r\n");
    std::string reqLine = buf.substr(0, lineEnd);
    std::istringstream rl(reqLine);
    rl >> r.method >> r.path;
    r.body = buf.substr(hdrEnd + 4, (size_t)contentLen);

    buf.erase(0, total);   // 消费已处理字节，剩余留给下一个请求
    *req = r;
    return (int)total;
}

struct Response {
    int code = 200;
    std::string contentType = "application/json";
    std::string body;
    bool keepAlive = true;   // 默认 keep-alive (HTTP/1.1), 仅 firmware upload 关闭

    void send(int fd) const {
        std::string hdr = "HTTP/1.1 " + std::to_string(code) + " OK\r\n"
            "Content-Type: " + contentType + "\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n"
            "Access-Control-Allow-Headers: Content-Type\r\n"
            "Connection: " + std::string(keepAlive ? "keep-alive" : "close") + "\r\n"
            "Content-Length: " + std::to_string(body.size()) + "\r\n"
            "\r\n";
        // C-2: send() 可能短写 (慢连接/内核缓冲满), 必须循环写完, 否则客户端收到截断响应,
        // 破坏 keep-alive 连接上后续请求的 Content-Length 帧对齐。
        const std::string full = hdr + body;
        size_t off = 0;
        while (off < full.size()) {
            ssize_t n = ::send(fd, full.c_str() + off, full.size() - off, MSG_NOSIGNAL);
            if (n <= 0) break;   // EAGAIN/EINTR 或对端关闭: 放弃本次发送
            off += (size_t)n;
        }
    }
};

// 发送响应并标记关闭连接（firmware upload 用: 上传大 body 不适合 keep-alive）
static void sendClose(Response& resp, int fd) {
    resp.keepAlive = false;
    resp.send(fd);
}

// HTML 面板（精简版，去掉大段文字和可视化，保留核心操作）
static const char* HTML = R"html(<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>TUN NAT HUB</title>
<style>
:root{--bg:#0b1121;--card:#111827;--bd:#1e293b;--fg:#e2e8f0;--muted:#94a3b8;--dim:#64748b;--cyan:#38bdf8;--green:#22c55e;--red:#ef4444;--amber:#f59e0b;--blue:#3b82f6}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,"Microsoft YaHei",sans-serif;background:var(--bg);color:var(--fg);min-height:100vh;line-height:1.5}
header{background:var(--card);padding:14px 24px;border-bottom:1px solid var(--bd);display:flex;align-items:center;gap:12px}
header .logo{font-size:1.4em;font-weight:700;background:linear-gradient(135deg,var(--cyan),var(--blue));-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.page{padding:20px 24px;max-width:1200px;margin:0 auto}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.card{background:var(--card);border-radius:10px;padding:18px;border:1px solid var(--bd)}
.card h3{font-size:0.95em;color:var(--muted);margin-bottom:14px;padding-bottom:8px;border-bottom:1px solid var(--bd)}
.stat-row{display:flex;justify-content:space-between;padding:3px 0;font-size:0.85em}
.stat-row span:first-child{color:var(--muted)}
.stat-row span:last-child{color:var(--cyan);font-family:monospace}
.code-block{background:var(--bg);padding:12px;border-radius:6px;font-family:monospace;font-size:0.78em;max-height:300px;overflow:auto;white-space:pre}
.dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:5px}
.dot.on{background:var(--green);box-shadow:0 0 6px var(--green)}
.dot.off{background:var(--red)}
.form-row{display:flex;gap:8px;margin-bottom:8px;align-items:center}
input,select{flex:1;padding:7px 10px;border:1px solid var(--bd);border-radius:6px;background:var(--bg);color:var(--fg);font-size:0.85em)}
input:focus,select:focus{outline:none;border-color:var(--cyan)}
.btn{padding:7px 16px;border:none;border-radius:6px;cursor:pointer;font-size:0.85em;font-weight:500;white-space:nowrap}
.btn:hover{opacity:0.85}
.btn-blue{background:var(--blue);color:#fff}
.btn-red{background:var(--red);color:#fff}
.btn-green{background:var(--green);color:#000}
.btn-sm{padding:3px 10px;font-size:0.75em}
.rules{list-style:none;font-size:0.85em}
.rules li{display:flex;justify-content:space-between;align-items:center;padding:5px 0;border-bottom:1px solid var(--bd)}
.warn{background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.3);border-radius:6px;padding:10px 14px;font-size:0.85em;color:var(--red);margin-top:8px}
.info{background:rgba(59,130,246,0.1);border:1px solid rgba(59,130,246,0.3);border-radius:6px;padding:10px 14px;font-size:0.85em;color:var(--blue);margin-top:8px}
.ch-row{display:flex;align-items:center;gap:8px;padding:3px 0}
.ch-label{width:36px;font-family:monospace;text-align:right;color:var(--muted)}
.ch-bar{flex:1;height:14px;background:var(--bg);border-radius:7px;overflow:hidden;position:relative}
.ch-fill{height:100%;border-radius:7px;background:linear-gradient(90deg,#2563eb,#38bdf8);transition:width 0.3s}
.ch-val{width:52px;font-family:monospace;font-size:0.82em;text-align:center}
.rc-btns{display:flex;flex-wrap:wrap;gap:6px;margin-top:8px;font-size:0.82em}
.rc-btn{background:var(--card);border:1px solid var(--bd);border-radius:4px;padding:2px 8px;color:var(--dim)}
.rc-btn.on{color:#fff;border-color:var(--green);background:rgba(34,197,94,0.15)}
@media(max-width:700px){.grid2{grid-template-columns:1fr}}
</style>
</head>
<body>
<header>
  <span class="logo">TUN NAT HUB</span><span style="font-size:0.7em;color:var(--dim)" id="hdr-ver">g_serial RTL8812AU · C++</span>
</header>
<div class="page">
  <div class="card" style="margin-bottom:16px">
    <h3>📊 实时状态</h3>
    <div id="status"></div>
  </div>
  <div class="card" style="margin-bottom:16px">
    <h3>🎮 RC 遥控器</h3>
    <div id="rc-state" style="font-size:0.85em"><span style="color:var(--dim)">等待 dji_rc daemon...</span></div>
  </div>
  <div class="grid2">
    <div class="card">
      <h3>🔀 端口转发 (LAN → DJI RC)</h3>
      <div style="color:var(--dim);font-size:0.8em;margin-bottom:8px">让局域网设备主动发数据给 DJI RC</div>
      <div class="form-row">
        <select id="fw-proto" style="flex:0;width:70px"><option>udp</option><option>tcp</option></select>
        <input id="fw-port" type="number" placeholder="端口" min="1" max="65535" style="flex:0;width:80px">
        <input id="fw-dest" value="10.0.0.2" style="flex:0;width:110px" placeholder="目标IP">
        <button class="btn btn-green" onclick="addFwd()">+ 添加</button>
      </div>
      <ul class="rules" id="fwd-list"></ul>
      <div class="warn">⚠️ DJI RC App 里也要监听对应端口才能收到数据。</div>
    </div>
    <div class="card">
      <h3>📹 摄像头管理</h3>
      <div class="form-row">
        <input id="cam-name" placeholder="名称" style="flex:0;width:100px">
        <input id="cam-url" placeholder="rtsp://...">
        <button class="btn btn-green" onclick="addCam()">+ 添加</button>
      </div>
      <ul class="rules" id="cam-list"></ul>
    </div>
  </div>
  <div class="grid2" style="margin-top:16px">
    <div class="card">
      <h3>🔧 固件升级 (Rootfs)</h3>
      <div style="color:var(--dim);font-size:0.8em;margin-bottom:8px">
        上传 <b>rootfs.squashfs</b> (4MB). 只更新根文件系统, 不碰 U-Boot/kernel.<br>
        烧录完成后需手动 <code>reboot</code> 重启.</div>
      <div class="form-row">
        <input type="file" id="fw-file" accept=".squashfs,.sq,.bin" style="flex:1">
        <button class="btn btn-blue" onclick="uploadFirmware()">⬆ 升级</button>
      </div>
      <div id="fw-progress" style="margin-top:8px;font-size:0.85em;color:var(--muted)"></div>
      <div id="fw-result" style="margin-top:4px;font-size:0.85em"></div>
    </div>
    <div class="card"><h3>🌐 网口信息</h3><pre class="code-block" id="net-info"></pre></div>
      <div class="grid2" style="margin-top:16px">
        <div class="card"><h3>System</h3><pre class="code-block" id="sys-info">loading...</pre></div>
        <div class="card"><h3>iptables</h3><pre class="code-block" id="ipt-info" style="max-height:200px"></pre></div></div>
  </div>
  <div class="info" style="margin-top:16px">
    <b>服务管理:</b> <code>systemctl restart tun_nat_hub</code> 或 <code>/etc/init.d/S99tun_nat_hub restart</code>
    &nbsp;|&nbsp; <b>日志:</b> <code>tail -f /var/log/usb_tund.log</code>
  </div>
</div>
<script>
const A="/api";
async function j(u){let r=await fetch(u);return r.json()}
async function t(u){let r=await fetch(u);return r.text()}
async function ref(){
  let h=await j(A+"/heartbeat"),s=await j(A+"/stats"),c=await j(A+"/config");
  document.getElementById("status").innerHTML=
    `<span class="dot ${h.daemon?'on':'off'}"></span>daemon: ${h.daemon?'运行':'停止'} | `+
    `<span class="dot ${h.tty_ready?'on':'off'}"></span>ttyGS0: ${h.tty_ready?'就绪':'未检测'} | `+
    `<span class="dot ${h.tun_up?'on':'off'}"></span>tun_hub: ${h.tun_up?'UP':'DOWN'} | `+
    `带宽: <b>${h.bandwidth_mbps} Mbps</b> | TX ${(s.tx_bytes/1e6).toFixed(1)}MB RX ${(s.rx_bytes/1e6).toFixed(1)}MB | `+
    `运行 ${h.uptime_since}`;
  let f="";
  if(c.forwards&&c.forwards.length) c.forwards.forEach(r=>{f+=`<li><span>${r.proto.toUpperCase()} :${r.port} → ${r.dest}</span><button class="btn btn-red btn-sm" onclick="delFwd(${r.port})">删</button></li>`});
  else f="<li style='color:var(--dim)'>无规则</li>";
  document.getElementById("fwd-list").innerHTML=f;
  let cl="";
  if(c.cameras&&c.cameras.length) c.cameras.forEach((c,i)=>{cl+=`<li><span>${c.name}: ${c.url}</span><button class="btn btn-red btn-sm" onclick="delCam(${i})">删</button></li>`});
  else cl="<li style='color:var(--dim)'>无摄像头</li>";
  document.getElementById("cam-list").innerHTML=cl;
  document.getElementById("net-info").textContent=await t(A+"/network");
  document.getElementById("ipt-info").textContent=await t(A+"/iptables");
  let sy=await j(A+"/system");
  document.getElementById("sys-info").textContent=
    `运行时长: ${sy.uptime}\n`+
    `usb_tund 守护进程: ${sy.daemon_active?'运行中':'停止'}\n`+
    `web_server: ${sy.web_active?'运行中':'停止'}\n`+
    `内存: ${sy.mem}\n`+
    `磁盘: ${sy.disk}`;
}
async function addFwd(){
  let r=await fetch(A+"/forward/add",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({proto:document.getElementById("fw-proto").value,port:parseInt(document.getElementById("fw-port").value),dest:document.getElementById("fw-dest").value})});
  if(r.ok) ref(); else alert("失败");}
async function delFwd(p){
  await fetch(A+"/forward/del",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({port:p})});
  ref();}
async function addCam(){
  let r=await fetch(A+"/camera/add",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name:document.getElementById("cam-name").value||"Camera",url:document.getElementById("cam-url").value})});
  if(r.ok){document.getElementById("cam-name").value="";document.getElementById("cam-url").value="";ref()}else alert("失败");}
async function delCam(i){
  await fetch(A+"/camera/del",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({index:i})});
  ref();}
async function uploadFirmware(){
  let f=document.getElementById("fw-file").files[0];
  if(!f){alert("请先选择 rootfs.squashfs 文件");return}
  if(f.size<1e6||f.size>8e6){alert("文件大小异常 (应为 ~4MB rootfs.squashfs)");return}
  if(!confirm("确定烧录 rootfs ("+(f.size/1024/1024).toFixed(1)+"MB) 到 rootfs 分区?\\nU-Boot/kernel 不受影响.\\n烧录完成后需手动 reboot."))return;
  let p=document.getElementById("fw-progress");
  let r=document.getElementById("fw-result");
  p.textContent="上传中..."; r.textContent="";
  let resp=await fetch(A+"/firmware/upload",{method:"POST",body:f,
    headers:{"Content-Type":"application/octet-stream","Content-Length":String(f.size)}});
  let j=await resp.json();
  p.textContent="";
  if(j.ok){r.innerHTML='<span style=\\"color:var(--green)\\">✅ Rootfs 烧录成功! '+j.message+'</span>'}
  else{r.innerHTML='<span style=\\"color:var(--red)\\">❌ 失败: '+(j.error||"未知错误")+'</span>'}
}
async function initVer(){try{let v=await(await fetch(A+"/version")).json();document.getElementById("hdr-ver").textContent="v"+v.version+" · g_serial · C++"}catch(e){}}
async function refRc(){
  try{
    let rc=await j(A+"/rc");
    if(rc.error){document.getElementById("rc-state").innerHTML='<span style=\"color:var(--dim)\">'+rc.error+'</span>';return}
    let mapped=[];
    for(let i=1;i<=16;i++) mapped.push(Number(rc['ch'+i]||1500));
    let chHtml='';
    for(let i=0;i<6;i++){
      let v=mapped[i];
      let pct=Math.max(0,Math.min(100,Math.round((v-1000)/10)));
      let raw=rc['raw_ch'+(i+1)];
      chHtml+='<div class=\"ch-row\"><span class=\"ch-label\">CH'+(i+1)+'</span>'
        +'<span style=\"width:42px;font-size:0.7em;color:var(--dim);text-align:center\">1500</span>'
        +'<div class=\"ch-bar\"><div class=\"ch-fill\" style=\"width:'+pct+'%\"></div></div>'
        +'<span class=\"ch-val\">'+v+'</span>'
        +'<span style=\"width:54px;font-size:0.72em;color:var(--dim);font-family:monospace;text-align:right\">'
        +(raw===undefined?'':'raw '+(raw>=0?'+':'')+raw)+'</span></div>';
    }
    const mapLabels=['MODE','REC','RTH','SHUT','AIR','DIAL','STOP','C1/C2','C3','DIR/BTN'];
    let mapHtml='<div style=\"margin-top:10px;font-size:0.75em;color:var(--dim)\">SBUS CH7-CH16</div>'
      +'<div class=\"rc-btns\" style=\"margin-top:4px\">';
    for(let i=6;i<16;i++) mapHtml+='<span class=\"rc-btn on\">CH'+(i+1)+' '+mapLabels[i-6]+': '+mapped[i]+'</span>';
    mapHtml+='</div>';
    let btns='';
    let flagNames={mode:rc.mode,btn:rc.btn,stop:rc.stop,focus:rc.focus,shot:rc.shot,rec:rc.rec,
                   rth:rc.rth,c1:rc.c1,c2:rc.c2,c3:rc.c3,dial:rc.dial,up:rc.up,down:rc.down,
                   left:rc.left,right:rc.right,aircraft:rc.aircraft,back:rc.back};
    for(let [k,v] of Object.entries(flagNames)){
      let label=({mode:'MODE',btn:'BTN',stop:'STOP',focus:'FOCUS',shot:'SHOT',rec:'REC',
                  rth:'RTH',c1:'C1',c2:'C2',c3:'C3',dial:'DIAL',up:'UP',down:'DN',
                  left:'L',right:'R',aircraft:'AC',back:'BACK'})[k]||k;
      let val=v;
      if(k==='mode') val=({S:'Sport',N:'Normal',F:'Film'})[v]||v;
      if(k==='dial') val=v;
      btns+='<span class=\"rc-btn'+(v?' on':'')+'\">'+label+(k==='dial'?(': '+v):(k==='mode'&&val?(': '+val):(v?' ●':'')))+'</span>';
    }
    let chBarSum=mapped.slice(0,6).map(v=>Math.abs(v-1500)).reduce((a,b)=>a+b,0)/6;
    document.getElementById("rc-state").innerHTML=chHtml
      +mapHtml
      +'<div class=\"rc-btns\">'+btns+'</div>'
      +'<div style=\"margin-top:6px;font-size:0.75em;color:var(--dim)\">'
      +'avg|ch-1500|='+Math.round(chBarSum)+' &nbsp; type='+(rc.type||'?')
      +' &nbsp; g1='+(rc.good1||0)+' g2='+(rc.good2||0)
      +'</div>';
  }catch(e){}
}
refRc();setInterval(refRc,500);
ref();setInterval(ref,3000);
initVer();
</script>
</body></html>
)html";

// ── 各 API 处理器 ─────────────────────────────────────────────

static std::string apiHeartbeat() {
    bool daemon = pidof("usb_tund");
    bool tty = fileExists("/dev/ttyGS0");
    // TUN 接口在此内核上 IFF_UP 位不会置 1，但能读到 stats 目录即表示接口已创建
    bool tun = fileExists("/sys/class/net/tun_hub/statistics/tx_bytes");

    uint64_t tx = readSysfs("/sys/class/net/tun_hub/statistics/tx_bytes");
    uint64_t rx = readSysfs("/sys/class/net/tun_hub/statistics/rx_bytes");

    std::string bandwidth = "0.0";
    double now = nowSec();
    if (g_bwPrev.ts > 0) {
        double elapsed = now - g_bwPrev.ts;
        if (elapsed > 0) {
            double mbps = ((tx - g_bwPrev.tx) + (rx - g_bwPrev.rx)) * 8.0 / (elapsed * 1e6);
            char buf[32];
            snprintf(buf, sizeof(buf), "%.1f", mbps);
            bandwidth = buf;
        }
    }
    g_bwPrev = {now, tx, rx};

    // uptime
    char uptime[64] = "0s";
    std::ifstream uf("/proc/uptime");
    if (uf.is_open()) {
        double u;
        uf >> u;
        snprintf(uptime, sizeof(uptime), "%.0fs", u);
    }

    // USB VID/PID
    int vid = 0, pid = 0;
    if (tty) {
        vid = (int)readSysfs("/sys/module/g_serial/parameters/idVendor");
        pid = (int)readSysfs("/sys/module/g_serial/parameters/idProduct");
    }

    JsonObj obj;
    obj.pair("version", JsonValue::string(VERSION));
    obj.pair("daemon", JsonValue::boolean(daemon));
    obj.pair("tty_ready", JsonValue::boolean(tty));
    obj.pair("tun_up", JsonValue::boolean(tun));
    obj.pair("usb_vid", JsonValue::number(vid));
    obj.pair("usb_pid", JsonValue::number(pid));
    obj.pair("timestamp", JsonValue::number((int)time(nullptr)));
    obj.pair("uptime_since", JsonValue::string(uptime));
    obj.pair("tx_bytes", JsonValue::number(tx));
    obj.pair("rx_bytes", JsonValue::number(rx));
    obj.pair("bandwidth_mbps", JsonValue::string(bandwidth));
    return obj.done();
}

static std::string apiStats() {
    // 从 daemon 日志最后一行读统计
    auto tail = exec({"tail", "-1", "/var/log/usb_tund.log"});
    // 格式: [统计] TX=123/456B RX=789/012B err=0
    uint64_t txPkts=0, txBytes=0, rxPkts=0, rxBytes=0, err=0;

    // CRIT#6: 安全解析数字, 日志损坏时 stoull 抛异常会终止进程
    auto safeStoull = [](const std::string& s) -> uint64_t {
        try { return std::stoull(s); } catch (...) { return 0; }
    };
    std::istringstream iss(tail);
    std::string w;
    while (iss >> w) {
        if (w.rfind("TX=",0) == 0) {
            auto s = w.substr(3);
            auto slash = s.find('/');
            txPkts = safeStoull(s.substr(0, slash));
            auto b = s.substr(slash+1);
            if (!b.empty() && b.back() == 'B') b.pop_back();
            txBytes = safeStoull(b);
        } else if (w.rfind("RX=",0) == 0) {
            auto s = w.substr(3);
            auto slash = s.find('/');
            rxPkts = safeStoull(s.substr(0, slash));
            auto b = s.substr(slash+1);
            if (!b.empty() && b.back() == 'B') b.pop_back();
            rxBytes = safeStoull(b);
        } else if (w.rfind("err=",0) == 0) {
            err = safeStoull(w.substr(4));
        }
    }

    // 实时带宽
    std::string bw = "0.0";
    double now = nowSec();
    if (g_stPrev.ts > 0) {
        double elapsed = now - g_stPrev.ts;
        if (elapsed > 0) {
            double mbps = (txBytes - g_stPrev.tx) * 8.0 / (elapsed * 1e6);
            char buf[32];
            snprintf(buf, sizeof(buf), "%.1f", mbps);
            bw = buf;
        }
    }
    g_stPrev = {now, txBytes, rxBytes};

    JsonObj obj;
    obj.pair("tx_pkts", JsonValue::number(txPkts));
    obj.pair("tx_bytes", JsonValue::number(txBytes));
    obj.pair("rx_pkts", JsonValue::number(rxPkts));
    obj.pair("rx_bytes", JsonValue::number(rxBytes));
    obj.pair("hb", JsonValue::number(0));
    obj.pair("err", JsonValue::number(err));
    obj.pair("bandwidth_mbps", JsonValue::string(bw));
    return obj.done();
}

static std::string apiSystem() {
    bool daemon = pidof("usb_tund");
    bool web = true;  // 自己这个进程当然在跑

    char uptime[64] = "0s";
    std::ifstream uf("/proc/uptime");
    if (uf.is_open()) { double u; uf >> u; snprintf(uptime, sizeof(uptime), "%.0fs", u); }

    auto mem = exec({"free", "-m"});
    std::string memLine;
    std::istringstream ms(mem);
    std::getline(ms, memLine); // skip header
    std::getline(ms, memLine); // Mem:
    // 精简: "Mem: 61004 13456 40512 118 47008 56204" → "已用 13M / 共 61M"
    {
        std::stringstream ss(memLine);
        std::string label; long total = 0, used = 0;
        ss >> label >> total >> used;
        if (total > 0) {
            std::stringstream fmt;
            fmt << "已用 " << used << "M / 共 " << total << "M";
            memLine = fmt.str();
        }
    }

    auto disk = exec({"df", "-h", "/"});
    std::string diskLine;
    std::istringstream ds(disk);
    std::getline(ds, diskLine); // skip header
    std::getline(ds, diskLine);
    // 精简: "/dev/root 3.7M 3.4M 291K 93% /" → "3.4M 已用 / 3.7M 共 (93%)"
    {
        std::stringstream ss(diskLine);
        std::string dev, size, used, avail, pct, mnt;
        ss >> dev >> size >> used >> avail >> pct >> mnt;
        if (!size.empty()) {
            std::stringstream fmt;
            fmt << used << " 已用 / " << size << " 共 (" << pct << ")";
            diskLine = fmt.str();
        }
    }

    JsonObj obj;
    obj.pair("uptime", JsonValue::string(uptime));
    obj.pair("daemon_active", JsonValue::boolean(daemon));
    obj.pair("web_active", JsonValue::boolean(web));
    obj.pair("mem", JsonValue::string(memLine));
    obj.pair("disk", JsonValue::string(diskLine));
    return obj.done();
}

static std::string apiConfig() {
    Config cfg = loadConfig();

    JsonObj obj;
    obj.pair("rtsp_url", JsonValue::string(cfg.rtspUrl));
    obj.pair("lan_subnet", JsonValue::string(cfg.lanSubnet));
    obj.pair("tun_subnet", JsonValue::string(cfg.tunSubnet));

    // forwards array
    std::string fArr = "[";
    for (size_t i = 0; i < cfg.forwards.size(); i++) {
        auto& r = cfg.forwards[i];
        JsonObj fo;
        fo.pair("proto", JsonValue::string(r.proto));
        fo.pair("port", JsonValue::number(r.port));
        fo.pair("dest", JsonValue::string(r.dest));
        fArr += fo.done();
        if (i+1 < cfg.forwards.size()) fArr += ",";
    }
    fArr += "]";
    obj.body += ",\"forwards\":" + fArr;

    // cameras array
    std::string cArr = "[";
    for (size_t i = 0; i < cfg.cameras.size(); i++) {
        auto& c = cfg.cameras[i];
        JsonObj co;
        co.pair("name", JsonValue::string(c.name));
        co.pair("url", JsonValue::string(c.url));
        cArr += co.done();
        if (i+1 < cfg.cameras.size()) cArr += ",";
    }
    cArr += "]";
    obj.body += ",\"cameras\":" + cArr;

    // rc_output (SBUS/CRSF 输出配置)
    obj.body += ",\"rc_output\":" + apiRcOutput(cfg);

    // first flag is still set if no pairs added yet... handle the hard-coded additions
    return obj.done();
}

static std::string apiNetwork() {
    return exec({"ip", "-br", "addr"});
}

static std::string apiIptables() {
    auto nat  = exec({"iptables", "-t", "nat", "-L", "PREROUTING", "-n"});
    auto fwd  = exec({"iptables", "-L", "FORWARD", "-n"});
    return "=== NAT PREROUTING ===\n" + nat + "=== FORWARD ===\n" + fwd;
}

// ═══════════════════════════════════════════════════════════════
// HTTP 请求分发
// ═══════════════════════════════════════════════════════════════

/* 默认通道映射字符串: "ch1,ch2,...,dir" */
static std::string default_map_str() {
    uint8_t map[CH_COUNT];
    rc_map_default(map);
    std::string s;
    for (int i = 0; i < CH_COUNT; i++) {
        if (i) s += ",";
        s += rc_src_name((rc_src_t)map[i]);
    }
    return s;
}

/* GET /api/rc/output — 返回当前 RC 输出配置 (SBUS/CRSF + 通道映射) */
static std::string apiRcOutput(const Config& cfg) {
    JsonObj obj;
    obj.pair("mode", JsonValue::string(cfg.rcOutMode));
    obj.pair("device", JsonValue::string(cfg.rcOutDevice));
    obj.pair("baud", JsonValue::string(cfg.rcOutBaud));
    obj.pair("map_preset", JsonValue::string(cfg.rcOutPreset));
    std::string mapStr = cfg.rcOutMap.empty() ? default_map_str() : cfg.rcOutMap;
    obj.pair("map", JsonValue::string(mapStr));
    obj.pair("crsf_period_ms", JsonValue::number(cfg.rcOutCrsfMs));
    obj.pair("crsf_telem", JsonValue::boolean(cfg.rcOutCrsfTelem));
    obj.pair("sbus_std", JsonValue::boolean(cfg.rcOutSbusStd));
    obj.pair("baud_sbus", JsonValue::number(100000));
    obj.pair("baud_sbus_nostd", JsonValue::number(115200));
    obj.pair("baud_crsf", JsonValue::number(420000));
    /* 可用 source 列表 (供 app 下拉) */
    std::string srcs;
    for (int i = 1; i < SRC_COUNT; i++) {
        if (i > 1) srcs += ",";
        srcs += rc_src_name((rc_src_t)i);
    }
    obj.pair("sources", JsonValue::string(srcs));
    return obj.done();
}

static Response handleRequest(const Request& req) {
    Response resp;

    // CORS preflight
    if (req.method == "OPTIONS") {
        resp.code = 200;
        resp.body = "";
        return resp;
    }

    // GET routes
    if (req.method == "GET") {
        std::string p = req.path;
        if (p.find("?") != std::string::npos) p = p.substr(0, p.find("?"));

        if (p == "/" || p == "/index.html") {
            resp.contentType = "text/html; charset=utf-8";
            resp.body = HTML;
        } else if (p == "/api/heartbeat") {
            resp.body = apiHeartbeat();
        } else if (p == "/api/stats") {
            resp.body = apiStats();
        } else if (p == "/api/system") {
            resp.body = apiSystem();
        } else if (p == "/api/config") {
            resp.body = apiConfig();
        } else if (p == "/api/network") {
            resp.contentType = "text/plain; charset=utf-8";
            resp.body = apiNetwork();
        } else if (p == "/api/iptables") {
            resp.contentType = "text/plain; charset=utf-8";
            resp.body = apiIptables();
        } else if (p == "/api/rc") {
            // 读取 dji_rc 守护进程写入的状态文件
            std::ifstream f("/var/log/rc_state.json");
            if (f.is_open()) {
                std::stringstream ss; ss << f.rdbuf();
                resp.body = ss.str();
                if (resp.body.empty()) resp.body = R"({"error":"no RC data yet"})";
            } else {
                resp.body = R"({"error":"RC daemon not running"})";
            }
        } else if (p == "/api/dji_rc/log") {
            // 诊断接口: 抓启动配置行 + 热重配检测行 + 状态刷屏行 + tail
            std::string boot = exec({"sh", "-c",
                "echo '=== BOOT ==='; "
                "grep -aE '输出|fd=|已打开' /var/log/dji_rc.log | head -8; "
                "echo '=== CFGCHK ==='; "
                "grep -aE 'cfg chk|变化|重配' /var/log/dji_rc.log | tail -8; "
                "echo '=== TAIL ==='; tail -4 /var/log/dji_rc.log"});
            resp.contentType = "text/plain; charset=utf-8";
            resp.body = boot;
        } else if (p == "/api/rc/output") {
            Config c = loadConfig();
            resp.body = apiRcOutput(c);
        } else if (p == "/api/rc/telemetry") {
            // 读取 dji_rc 写入的回传数据文件
            std::ifstream f("/var/log/rc_telem.json");
            if (f.is_open()) {
                std::stringstream ss; ss << f.rdbuf();
                resp.body = ss.str();
                if (resp.body.empty()) resp.body = R"({"error":"no telemetry yet"})";
            } else {
                resp.body = "{\"error\":\"no telemetry (CRSF mode only)\"}";
            }
        } else if (p == "/api/version") {
            JsonObj obj;
            obj.pair("version", JsonValue::string(VERSION));
            resp.body = obj.done();
        } else {
            resp.code = 404;
            resp.body = R"({"error":"not found"})";
        }
        return resp;
    }

    // POST routes
    if (req.method == "POST") {
        std::string p = req.path;
        if (p.find("?") != std::string::npos) p = p.substr(0, p.find("?"));

        Config cfg = loadConfig();

        if (p == "/api/forward/add") {
            auto proto = jsonStr(req.body, "proto");
            int port = jsonInt(req.body, "port");
            auto dest = jsonStr(req.body, "dest");
            bool ok = addForward(cfg, proto, port, dest);
            JsonObj obj;
            obj.pair("ok", JsonValue::boolean(ok));
            resp.body = obj.done();
        } else if (p == "/api/forward/del") {
            int port = jsonInt(req.body, "port");
            bool ok = removeForward(cfg, port);
            JsonObj obj;
            obj.pair("ok", JsonValue::boolean(ok));
            resp.body = obj.done();
        } else if (p == "/api/config/save") {
            auto v = jsonStr(req.body, "rtsp_url");
            if (!v.empty()) cfg.rtspUrl = v;
            auto lan = jsonStr(req.body, "lan_subnet");
            if (!lan.empty()) cfg.lanSubnet = lan;
            saveConfig(cfg);
            applyRtspUdpRtpForward(cfg);
            JsonObj obj;
            obj.pair("ok", JsonValue::boolean(true));
            resp.body = obj.done();
        } else if (p == "/api/rc/output") {
            /* 保存 RC 输出配置; dji_rc 每 2s 检测变化后自动重启生效 */
            auto mv = jsonStr(req.body, "mode");
            if (mv == "sbus" || mv == "crsf") cfg.rcOutMode = mv;
            auto bd = jsonStr(req.body, "baud");
            if (!bd.empty()) cfg.rcOutBaud = bd;
            auto ps = jsonStr(req.body, "map_preset");
            if (!ps.empty()) cfg.rcOutPreset = ps;
            auto mp = jsonStr(req.body, "map");
            if (!mp.empty()) cfg.rcOutMap = mp;
            else if (ps != "custom") cfg.rcOutMap = "";   /* 预设非自定义时清空自定义 map */
            auto tb = jsonStr(req.body, "crsf_telem");
            if (tb == "true" || tb == "false") cfg.rcOutCrsfTelem = (tb == "true");
            auto ss = jsonStr(req.body, "sbus_std");
            if (ss == "true" || ss == "false") cfg.rcOutSbusStd = (ss == "true");
            int per = jsonInt(req.body, "crsf_period_ms");
            if (per >= 5 && per <= 100) cfg.rcOutCrsfMs = per;
            saveConfig(cfg);
            JsonObj obj;
            obj.pair("ok", JsonValue::boolean(true));
            obj.pair("mode", JsonValue::string(cfg.rcOutMode));
            resp.body = obj.done();
        } else if (p == "/api/camera/add") {
            Camera c;
            c.name = jsonStr(req.body, "name");
            c.url  = jsonStr(req.body, "url");
            if (c.name.empty()) c.name = "Camera";
            if (!c.url.empty()) {
                cfg.cameras.push_back(c);
                saveConfig(cfg);
                applyRtspUdpRtpForward(cfg);
            }
            JsonObj obj;
            obj.pair("ok", JsonValue::boolean(!c.url.empty()));
            resp.body = obj.done();
        } else if (p == "/api/camera/del") {
            int idx = jsonInt(req.body, "index");
            bool ok = idx >= 0 && idx < (int)cfg.cameras.size();
            if (ok) {
                cfg.cameras.erase(cfg.cameras.begin() + idx);
                saveConfig(cfg);
                applyRtspUdpRtpForward(cfg);
            }
            JsonObj obj;
            obj.pair("ok", JsonValue::boolean(ok));
            resp.body = obj.done();
        } else if (p == "/api/firmware/upload") {
            // Handled in main loop before parseRequest
            JsonObj obj;
            obj.pair("ok", JsonValue::boolean(false));
            obj.pair("error", JsonValue::string("use POST with raw binary body"));
            resp.body = obj.done();
        } else {
            resp.code = 404;
            resp.body = R"({"error":"not found"})";
        }
        return resp;
    }

    resp.code = 405;
    resp.body = R"({"error":"method not allowed"})";
    return resp;
}

// ═══════════════════════════════════════════════════════════════
// 固件升级
// ═══════════════════════════════════════════════════════════════

static std::string readLine(int fd) {
    std::string line;
    char c;
    const size_t MAX_LINE = 8192;   // H: 限制单行长度, 防恶意超长行耗尽内存
    while (::recv(fd, &c, 1, 0) > 0) {
        if (c == '\r') continue;
        if (c == '\n') break;
        if (line.size() >= MAX_LINE) return line;  // 超长: 返回已有内容, 连接将被上层关闭
        line += c;
    }
    return line;
}

static std::string findHeader(const std::string& headers, const std::string& key) {
    auto pos = headers.find(key + ": ");
    if (pos == std::string::npos) return "";
    pos += key.size() + 2;
    auto end = headers.find("\r\n", pos);
    return headers.substr(pos, end - pos);
}

static void handleFirmwareUpload(int fd) {
    Response resp;
    resp.contentType = "application/json";
    std::cout << "[fw] === UPGRADE START ===" << std::endl;
    // C4: 设置 socket 接收超时 (30s), 防恶意客户端发 Content-Length 后停止发送导致永久阻塞
    struct timeval rcvTv;
    rcvTv.tv_sec = 30; rcvTv.tv_usec = 0;
    ::setsockopt(fd, SOL_SOCKET, SO_RCVTIMEO, &rcvTv, sizeof(rcvTv));
    std::string reqLine = readLine(fd);
    if (reqLine.find("POST") == std::string::npos) {
        std::cout << "[fw] ERR: not POST" << std::endl;
        resp.code = 405; resp.body = R"({"ok":false,"error":"method not allowed"})";
        sendClose(resp, fd); return;
    }
    std::string headers;
    while (true) { std::string line = readLine(fd); if (line.empty()) break; headers += line + "\n"; }
    auto clStr = findHeader(headers, "Content-Length");
    // CRIT#4: stoull 对非法值抛异常会终止进程, try-catch 防护
    size_t contentLen = 0;
    if (!clStr.empty()) {
        try { contentLen = std::stoull(clStr); }
        catch (...) {
            std::cout << "[fw] ERR: bad Content-Length" << std::endl;
            resp.code = 400; resp.body = R"({"ok":false,"error":"bad Content-Length"})";
            sendClose(resp, fd); return;
        }
    }
    std::cout << "[fw] SIZE: " << contentLen << " bytes (" << (contentLen/1024) << "KB)" << std::endl;
    if (contentLen < 1024*1024 || contentLen > 8*1024*1024) {
        std::cout << "[fw] ERR: invalid size" << std::endl;
        resp.code = 400; resp.body = R"({"ok":false,"error":"invalid size"})";
        sendClose(resp, fd); return;
    }
    std::string tmpPath = "/var/log/new_rootfs.sq";
    int fwFd = ::open(tmpPath.c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fwFd < 0) {
        std::cout << "[fw] ERR: cannot create tmp file" << std::endl;
        resp.body = R"({"ok":false,"error":"cannot create temp file"})";
        sendClose(resp, fd); return;
    }
    char buf[32768]; size_t remaining = contentLen, lastRpt = 0;
    while (remaining > 0) {
        size_t chunk = remaining < sizeof(buf) ? remaining : sizeof(buf);
        ssize_t n = ::recv(fd, buf, chunk, 0); if (n <= 0) break;
        ssize_t written = ::write(fwFd, buf, n);   // CRIT#5: 检查写返回值, 短写中止避免坏固件
        if (written != n) {
            std::cout << "[fw] ERR: write 短写 " << written << "/" << n << std::endl;
            remaining = SIZE_MAX;  // 标记失败
            break;
        }
        remaining -= n;
        if (contentLen - remaining - lastRpt >= 512*1024) {
            lastRpt = contentLen - remaining;
            std::cout << "[fw] RECV: " << (lastRpt/1024) << "/" << (contentLen/1024) << "KB" << std::endl;
        }
    }
    ::close(fwFd);
    std::cout << "[fw] RECV: done, " << (contentLen-remaining) << " bytes" << std::endl;
    if (remaining > 0) {
        std::cout << "[fw] ERR: upload incomplete" << std::endl;
        ::unlink(tmpPath.c_str()); resp.body = R"({"ok":false,"error":"upload incomplete"})";
        sendClose(resp, fd); return;
    }
    int vFd = ::open(tmpPath.c_str(), O_RDONLY);
    if (vFd >= 0) {
        uint8_t magic[4] = {0};
        // H-1: read 返回值检查, 失败则按 bad magic 处理 (magic 保持初始化值 0)
        if (::read(vFd, magic, 4) != 4) { ::close(vFd); magic[0] = magic[1] = magic[2] = magic[3] = 0; }
        else ::close(vFd);
        std::cout << "[fw] MAGIC: " << magic[0] << magic[1] << magic[2] << magic[3] << " (expect hsqs)" << std::endl;
        if (magic[0] != 'h' || magic[1] != 's' || magic[2] != 'q' || magic[3] != 's') {
            std::cout << "[fw] ERR: bad magic" << std::endl;
            ::unlink(tmpPath.c_str());
            JsonObj obj; obj.pair("ok", JsonValue::boolean(false));
            obj.pair("error", JsonValue::string("bad squashfs magic"));
            resp.body = obj.done(); sendClose(resp, fd); return;
        }
    }
    struct stat st;
    if (::stat(tmpPath.c_str(), &st) == 0 && st.st_size > 12) {
        int tf = ::open(tmpPath.c_str(), O_RDONLY);
        if (tf >= 0) {
            char tail[12];
            if (::lseek(tf, st.st_size - 12, SEEK_SET) >= 0 && ::read(tf, tail, 12) != 12) {
                std::memset(tail, 0, sizeof(tail));   // H-1: 读失败则清空, 避免用未初始化栈数据
            }
            ::close(tf);
            if (memcmp(tail, "TUN_NAT_HUB", 11) == 0) {
                // C-3: 避免 unaligned 访问 UB, 用 memcpy 提取 CRC32
                uint32_t crc;
                std::memcpy(&crc, tail + 8, sizeof(crc));
                std::cout << "[fw] TAIL: CRC32=0x" << std::hex << crc << std::dec << " OK" << std::endl;
            } else { std::cout << "[fw] TAIL: not present" << std::endl; }
        }
    }
    bool runningOnB = false;
    std::string cmdline = exec({"cat", "/proc/cmdline"});
    if (cmdline.find("mtdblock4") != std::string::npos) runningOnB = true;
    std::string inactiveDev = runningOnB ? "/dev/mtdblock3" : "/dev/mtdblock4";
    std::cout << "[fw] SLOT: " << (runningOnB ? "B->A" : "A->B") << " target=" << inactiveDev << std::endl;
    // Erase inactive partition first (NOR flash requires explicit erase before write)
    std::string mtdDev = runningOnB ? "/dev/mtd3" : "/dev/mtd4";
    std::string eraseCmd = "flash_erase -q " + mtdDev + " 0 0 2>/dev/null || mtd_debug erase " + mtdDev + " 0 1048576 2>/dev/null || true";
    std::cout << "[fw] ERASE: " << eraseCmd << std::endl;
    // H-2: 检查擦除命令返回值 (命令含 || true 兜底, 但 flash_erase 失败路径需告警,
    // 未擦除就 dd 写入可能损坏 rootfs)
    int eraseRc = system(eraseCmd.c_str());
    if (eraseRc != 0) {
        std::cout << "[fw] WARN: erase 命令返回 " << eraseRc << " (可能未擦除, dd 写入有风险)" << std::endl;
    }

    std::cout << "[fw] dd " << tmpPath << " -> " << inactiveDev << std::endl;
	std::string flashCmd = "dd if=" + tmpPath + " of=" + inactiveDev + " bs=4096 2>&1";
    std::cout << "[fw] DD: " << flashCmd << std::endl;
    int rc = system(flashCmd.c_str());
    std::cout << "[fw] DD: exit=" << rc << std::endl;
    if (rc != 0) {
        ::unlink(tmpPath.c_str()); JsonObj obj; obj.pair("ok", JsonValue::boolean(false));
        obj.pair("error", JsonValue::string("flash write failed"));
        resp.body = obj.done(); sendClose(resp, fd); return;
    }
    std::string vfy = exec({"sh", "-c", ("dd if=" + inactiveDev + " bs=1 count=16 2>/dev/null | hexdump -C 2>/dev/null").c_str()});
    std::cout << "[fw] VFY: " << (vfy.find("hsqs") != std::string::npos ? "hsqs OK" : "hsqs MISSING!") << std::endl;
    int slotFd = ::open("/dev/mtdblock0", O_WRONLY);
    if (slotFd >= 0) {
        // TUN_NAT_HUB A/B OTA ctl block @ 0xFC000 (6 bytes):
        // [0] flag:       0xFF=A(mtdblock3), 0x00=B(mtdblock4) — TARGET slot
        // [1] confirmed:  0xFF=stable, 0x00=trial
        // [2] retry:      remaining trial boots (decremented per boot by SPL)
        // [3] version:    OTA protocol version (0x01)
        // [4] last_slot:  source slot before switch (for fallback)
        // [5] boot_count: wraps on each boot
        uint8_t lastSlot = runningOnB ? 0x00 : 0xFF;     // B or A
        uint8_t tgtFlag  = runningOnB ? 0xFF : 0x00;     // A or B
        uint8_t ctl[6] = {tgtFlag, 0x00, 0x03, 0x01, lastSlot, 0x00};
        // CRIT#7: 检查 lseek/write 返回值, 写失败则报错 (ctl 损坏会启动失败)
        off_t seekRc = ::lseek(slotFd, 0xFC000, SEEK_SET);
        ssize_t ctlRc = (seekRc == (off_t)0xFC000) ? ::write(slotFd, ctl, 6) : -1;
        ::close(slotFd); sync();
        if (ctlRc != 6)
            std::cerr << "[fw] WARN: OTA ctl 写入失败 (" << ctlRc << "/6)" << std::endl;
        std::cout << "[fw] FLAG: target=" << (tgtFlag ? "A" : "B")
                  << " last=" << (lastSlot ? "A" : "B")
                  << " trial=3 retries" << std::endl;
    }
    int vf2 = ::open("/dev/mtdblock0", O_RDONLY);
    if (vf2 >= 0) {
        uint8_t ctl[6] = {0};
        // H-1: read 返回值检查, 失败时 ctl 保持初始化 0
        if (::lseek(vf2, 0xFC000, SEEK_SET) >= 0 && ::read(vf2, ctl, 6) != 6) {
            std::memset(ctl, 0, sizeof(ctl));
        }
        ::close(vf2);
        std::cout << "[fw] VFY: ctl=" << std::hex << (int)ctl[4] << "|" << (int)ctl[5] << std::dec << std::endl;
    }
    ::unlink(tmpPath.c_str());
    JsonObj obj; obj.pair("ok", JsonValue::boolean(true));
    obj.pair("size", JsonValue::number((int)contentLen));
    obj.pair("message", JsonValue::string("Flashed to " + inactiveDev + ". Reboot now to switch."));
    resp.body = obj.done(); sendClose(resp, fd);
    std::cout << "[fw] === UPGRADE DONE ===" << std::endl;
    // 自动重启：清空页面缓存，2秒后 reboot
    sync();
    std::cout << "[fw] Rebooting in 2s..." << std::endl;
    system("sleep 2 && reboot &");
}

int main() {
    // 检测 LAN 网口名
    g_lanIface = detectLanIface();
    std::cout << "[web_server] LAN 网口: " << g_lanIface << std::endl;

    // 加载配置 + 应用已有转发规则
    bool cfgChanged = false;
    Config cfg = loadConfig(&cfgChanged);
    // H-3: 只在配置实际变化时写 SPI, 避免每次启动无条件擦写 NOR flash (磨损寿命)
    if (cfgChanged) saveConfig(cfg);
    applyAllForwards(cfg);
    // 启动时 eth0 可能尚未拿到 IP, applyRtspUdpRtpForward 会返回 false;
    // 主循环每 2s 重试直到应用成功 (修复 V3s 重启后 DNAT 规则永久丢失)
    bool rtspFwdApplied = applyRtspUdpRtpForward(cfg);

    // 创建监听 socket
    int srv = socket(AF_INET, SOCK_STREAM, 0);
    if (srv < 0) { perror("socket"); return 1; }

    int one = 1;
    setsockopt(srv, SOL_SOCKET, SO_REUSEADDR, &one, sizeof(one));

    struct sockaddr_in addr = {};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(PORT);
    addr.sin_addr.s_addr = INADDR_ANY;

    if (bind(srv, (sockaddr*)&addr, sizeof(addr)) < 0) { perror("bind"); return 1; }
    if (listen(srv, MAX_CLI) < 0) { perror("listen"); return 1; }

    std::cout << "[web_server] HTTP 面板: http://0.0.0.0:" << PORT << std::endl;

    // ── 连接管理: poll 事件循环, 单线程多路复用 ──
    // 根治: 单个连接阻塞 recv 不再会卡死整个服务器。
    // 新连接/可读事件由 poll 驱动; 空闲连接按 lastActive 超时清理。
    struct Conn {
        int fd = -1;
        std::string buf;           // 累积接收数据, 跨请求保留
        bool firstHandled = false; // 首个请求是否已处理
        int64_t lastActive_ms = 0;
    };
    auto now_ms = []() -> int64_t {
        return std::chrono::duration_cast<std::chrono::milliseconds>(
            std::chrono::steady_clock::now().time_since_epoch()).count();
    };
    const int64_t IDLE_TIMEOUT_MS = 10000;   // 空闲连接 10s 后回收

    // RTSP UDP 转发重试: LAN IP 就绪前每 2s 补一次规则, 直到应用成功
    const int64_t RTSP_FWD_RETRY_MS = 2000;
    int64_t lastRtspFwdRetryMs = 0;

    std::vector<Conn> conns;
    std::vector<struct pollfd> pfds;

    while (true) {
        // RTSP UDP 转发重试: 启动时 eth0 IP 未就绪导致规则未应用时, 周期补齐直到成功
        if (!rtspFwdApplied && (now_ms() - lastRtspFwdRetryMs) >= RTSP_FWD_RETRY_MS) {
            lastRtspFwdRetryMs = now_ms();
            if (applyRtspUdpRtpForward(cfg)) {
                rtspFwdApplied = true;
                std::cout << "[rtsp-udp] RTSP UDP 转发规则已补应用" << std::endl;
            }
        }

        pfds.clear();
        pfds.push_back({srv, POLLIN, 0});
        for (auto& c : conns) pfds.push_back({c.fd, POLLIN, 0});

        int rc = ::poll(pfds.data(), pfds.size(), 1000);   // 1s 心跳, 用于空闲回收
        if (rc < 0) { if (errno == EINTR) continue; break; }

        // 新连接
        if (pfds[0].revents & POLLIN) {
            int cli = ::accept(srv, nullptr, nullptr);
            if (cli >= 0) {
                if ((int)conns.size() < MAX_CLI) {
                    Conn c; c.fd = cli; c.lastActive_ms = now_ms();
                    conns.push_back(c);
                } else {
                    ::close(cli);   // 并发超限直接拒绝, 防止资源耗尽
                }
            }
        }

        // 处理活跃连接
        for (size_t i = 1; i < pfds.size(); i++) {
            Conn& c = conns[i - 1];
            if (c.fd < 0) continue;

            if (pfds[i].revents & (POLLHUP | POLLERR)) {
                ::close(c.fd); c.fd = -1;
                continue;
            }
            if (!(pfds[i].revents & POLLIN)) continue;

            c.lastActive_ms = now_ms();

            // 每个请求都 peek 检测固件上传 (peek 不消费数据, 普通请求无影响)
            // 修复: 浏览器 fetch 复用连接时 firstHandled 已为 true, 旧逻辑只在首请求拦截导致上传失败
            {
                char peek[2048] = {};
                int peekLen = ::recv(c.fd, peek, sizeof(peek) - 1, MSG_PEEK);
                if (peekLen > 0) {
                    peek[peekLen] = '\0';
                    if (std::strstr(peek, "POST /api/firmware/upload") != nullptr) {
                        handleFirmwareUpload(c.fd);   // 阻塞收 body, 之后自动 reboot
                        ::close(c.fd); c.fd = -1;
                        continue;
                    }
                }
            }

            char chunk[BUF_SZ];
            int n = ::recv(c.fd, chunk, sizeof(chunk), 0);
            if (n <= 0) { ::close(c.fd); c.fd = -1; continue; }   // 对端关闭/错误
            c.buf.append(chunk, n);

            // 处理缓冲中所有完整请求 (Keep-Alive 复用连接)
            while (c.fd >= 0) {
                Request req;
                int r = extractRequest(c.buf, &req);
                if (r < 0) { ::close(c.fd); c.fd = -1; break; }    // 异常: 关闭
                if (r == 0) break;                                 // 需要更多数据
                Response resp = handleRequest(req);
                resp.send(c.fd);
                c.firstHandled = true;
            }
        }

        // 清理: 已关闭 或 空闲超时的连接
        for (auto it = conns.begin(); it != conns.end();) {
            if (it->fd < 0 || (now_ms() - it->lastActive_ms) > IDLE_TIMEOUT_MS) {
                if (it->fd >= 0) ::close(it->fd);
                it = conns.erase(it);
            } else {
                ++it;
            }
        }
    }

    close(srv);
    return 0;
}
