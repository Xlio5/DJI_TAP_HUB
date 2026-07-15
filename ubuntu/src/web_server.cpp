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
#include <sstream>
#include <string>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <thread>
#include <unistd.h>
#include <vector>

// ═══════════════════════════════════════════════════════════════
// 常量
// ═══════════════════════════════════════════════════════════════
constexpr int    PORT       = 8080;
constexpr int    BUF_SZ     = 8192;
constexpr int    MAX_CLI    = 8;
constexpr int    MAX_CFG    = 32768;
const char*      CFG_FILE   = "/root/tun_nat_hub_config.json";

// 带宽历史（用于计算实时 Mbps）
struct BwPrev {
    double time = 0;
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
    cmd += " 2>/dev/null";
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
    std::string rtspUrl = "rtsp://192.168.88.100:554/stream1";
    std::string lanSubnet = "192.168.88.0/24";
    std::string tunSubnet = "10.0.0.0/24";
    std::vector<ForwardRule> forwards;
    std::vector<Camera> cameras;
};

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

static Config loadConfig() {
    Config cfg;
    std::ifstream f(CFG_FILE);
    if (!f.is_open()) {
        auto detected = detectLanSubnet();
        if (!detected.empty()) cfg.lanSubnet = detected;
        return cfg;
    }
    std::string json((std::istreambuf_iterator<char>(f)),
                      std::istreambuf_iterator<char>());
    f.close();

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

    // 自动检测 LAN 网段变化
    auto detected = detectLanSubnet();
    if (!detected.empty() && detected != cfg.lanSubnet) {
        std::cout << "[web_server] LAN 网段自动检测: " << cfg.lanSubnet << " → " << detected << std::endl;
        cfg.lanSubnet = detected;
    }

    return cfg;
}

static void saveConfig(const Config& cfg) {
    std::ofstream f(CFG_FILE);
    if (!f.is_open()) return;
    f << "{\n";
    f << "  \"rtsp_url\": \"" << cfg.rtspUrl << "\",\n";
    f << "  \"lan_subnet\": \"" << cfg.lanSubnet << "\",\n";
    f << "  \"tun_subnet\": \"" << cfg.tunSubnet << "\",\n";
    f << "  \"forwards\": [\n";
    for (size_t i = 0; i < cfg.forwards.size(); i++) {
        auto& r = cfg.forwards[i];
        f << "    {\"proto\":\"" << r.proto << "\",\"port\":" << r.port << ",\"dest\":\"" << r.dest << "\"}";
        f << (i+1 < cfg.forwards.size() ? ",\n" : "\n");
    }
    f << "  ],\n";
    f << "  \"cameras\": [\n";
    for (size_t i = 0; i < cfg.cameras.size(); i++) {
        auto& c = cfg.cameras[i];
        f << "    {\"name\":\"" << c.name << "\",\"url\":\"" << c.url << "\"}";
        f << (i+1 < cfg.cameras.size() ? ",\n" : "\n");
    }
    f << "  ]\n}\n";
    f.close();
}

// ═══════════════════════════════════════════════════════════════
// iptables 转发管理
// ═══════════════════════════════════════════════════════════════

static std::string g_lanIface = "eth0";

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

static Request parseRequest(const char* raw, int len) {
    Request req;
    std::string data(raw, len);
    auto lineEnd = data.find("\r\n");
    if (lineEnd == std::string::npos) return req;
    std::string reqLine = data.substr(0, lineEnd);
    std::istringstream rl(reqLine);
    rl >> req.method >> req.path;

    // find body
    auto bodySep = data.find("\r\n\r\n");
    if (bodySep != std::string::npos) {
        req.body = data.substr(bodySep + 4);
    }
    return req;
}

struct Response {
    int code = 200;
    std::string contentType = "application/json";
    std::string body;

    void send(int fd) const {
        std::string hdr = "HTTP/1.1 " + std::to_string(code) + " OK\r\n"
            "Content-Type: " + contentType + "\r\n"
            "Access-Control-Allow-Origin: *\r\n"
            "Access-Control-Allow-Methods: GET, POST, OPTIONS\r\n"
            "Access-Control-Allow-Headers: Content-Type\r\n"
            "Connection: close\r\n"
            "Content-Length: " + std::to_string(body.size()) + "\r\n"
            "\r\n";
        ::send(fd, hdr.c_str(), hdr.size(), MSG_NOSIGNAL);
        ::send(fd, body.c_str(), body.size(), MSG_NOSIGNAL);
    }
};

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
@media(max-width:700px){.grid2{grid-template-columns:1fr}}
</style>
</head>
<body>
<header>
  <span class="logo">TUN NAT HUB</span><span style="font-size:0.7em;color:var(--dim)">g_serial RTL8812AU · C++</span>
</header>
<div class="page">
  <div class="card" style="margin-bottom:16px">
    <h3>📊 实时状态</h3>
    <div id="status"></div>
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
ref();setInterval(ref,3000);
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
    if (g_bwPrev.time > 0) {
        double elapsed = now - g_bwPrev.time;
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
    obj.pair("version", JsonValue::string("1.1.0"));
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

    std::istringstream iss(tail);
    std::string w;
    while (iss >> w) {
        if (w.rfind("TX=",0) == 0) {
            auto s = w.substr(3);
            auto slash = s.find('/');
            txPkts = std::stoull(s.substr(0, slash));
            auto b = s.substr(slash+1);
            if (!b.empty() && b.back() == 'B') b.pop_back();
            txBytes = b.empty() ? 0 : std::stoull(b);
        } else if (w.rfind("RX=",0) == 0) {
            auto s = w.substr(3);
            auto slash = s.find('/');
            rxPkts = std::stoull(s.substr(0, slash));
            auto b = s.substr(slash+1);
            if (!b.empty() && b.back() == 'B') b.pop_back();
            rxBytes = b.empty() ? 0 : std::stoull(b);
        } else if (w.rfind("err=",0) == 0) {
            err = std::stoull(w.substr(4));
        }
    }

    // 实时带宽
    std::string bw = "0.0";
    double now = nowSec();
    if (g_stPrev.time > 0) {
        double elapsed = now - g_stPrev.time;
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

    auto disk = exec({"df", "-h", "/"});
    std::string diskLine;
    std::istringstream ds(disk);
    std::getline(ds, diskLine); // skip header
    std::getline(ds, diskLine);

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
        } else if (p == "/api/version") {
            JsonObj obj;
            obj.pair("version", JsonValue::string("1.1.0"));
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
            JsonObj obj;
            obj.pair("ok", JsonValue::boolean(true));
            resp.body = obj.done();
        } else if (p == "/api/camera/add") {
            Camera c;
            c.name = jsonStr(req.body, "name");
            c.url  = jsonStr(req.body, "url");
            if (c.name.empty()) c.name = "Camera";
            if (!c.url.empty()) {
                cfg.cameras.push_back(c);
                saveConfig(cfg);
            }
            JsonObj obj;
            obj.pair("ok", JsonValue::boolean(!c.url.empty()));
            resp.body = obj.done();
        } else if (p == "/api/camera/del") {
            int idx = jsonInt(req.body, "index");
            if (idx >= 0 && idx < (int)cfg.cameras.size()) {
                cfg.cameras.erase(cfg.cameras.begin() + idx);
                saveConfig(cfg);
            }
            JsonObj obj;
            obj.pair("ok", JsonValue::boolean(idx >= 0 && idx < (int)cfg.cameras.size()));
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
    while (::recv(fd, &c, 1, 0) > 0) {
        if (c == '\r') continue;
        if (c == '\n') break;
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

    // Read request line
    std::string reqLine = readLine(fd);
    if (reqLine.find("POST") == std::string::npos) {
        resp.code = 405;
        resp.body = R"({"ok":false,"error":"method not allowed"})";
        resp.send(fd);
        return;
    }

    // Read all headers
    std::string headers;
    while (true) {
        std::string line = readLine(fd);
        if (line.empty()) break;
        headers += line + "\n";
    }

    auto clStr = findHeader(headers, "Content-Length");
    size_t contentLen = clStr.empty() ? 0 : std::stoull(clStr);

    // rootfs.squashfs is ~4MB, allow 1–8MB
    if (contentLen < 1024*1024 || contentLen > 8*1024*1024) {
        resp.code = 400;
        resp.body = R"({"ok":false,"error":"invalid size, expect rootfs.squashfs ~4MB"})";
        resp.send(fd);
        return;
    }

    // Stream body to /tmp/new_rootfs.sq
    std::string tmpPath = "/tmp/new_rootfs.sq";
    int fwFd = ::open(tmpPath.c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fwFd < 0) {
        resp.body = R"({"ok":false,"error":"cannot create temp file"})";
        resp.send(fd);
        return;
    }

    char buf[32768];
    size_t remaining = contentLen;
    while (remaining > 0) {
        size_t chunk = remaining < sizeof(buf) ? remaining : sizeof(buf);
        ssize_t n = ::recv(fd, buf, chunk, 0);
        if (n <= 0) break;
        ::write(fwFd, buf, n);
        remaining -= n;
    }
    ::close(fwFd);

    if (remaining > 0) {
        ::unlink(tmpPath.c_str());
        resp.body = R"({"ok":false,"error":"upload incomplete"})";
        resp.send(fd);
        return;
    }

    // Validate squashfs magic: first 4 bytes must be "hsqs"
    int vFd = ::open(tmpPath.c_str(), O_RDONLY);
    if (vFd >= 0) {
        uint8_t magic[4];
        ::read(vFd, magic, 4);
        ::close(vFd);
        if (magic[0] != 'h' || magic[1] != 's' || magic[2] != 'q' || magic[3] != 's') {
            ::unlink(tmpPath.c_str());
            JsonObj obj;
            obj.pair("ok", JsonValue::boolean(false));
            obj.pair("error", JsonValue::string("not a valid squashfs (no hsqs magic)"));
            resp.body = obj.done();
            resp.send(fd);
            return;
        }
    }

    // Flash to rootfs partition ONLY (mtdblock3) — does NOT touch U-Boot/kernel/DTB
    // fallback: write to raw /dev/mtd0 at offset 0x710000 if mtdblock3 doesn't exist
    std::string flashCmd;
    if (fileExists("/dev/mtdblock3")) {
        flashCmd = "dd if=" + tmpPath + " of=/dev/mtdblock3 bs=4096 2>&1";
    } else {
        // mtdparts may not be active — write to raw mtd0 at rootfs offset
        flashCmd = "dd if=" + tmpPath + " of=/dev/mtd0 bs=4096 seek=1808 2>&1";
    }
    std::cout << "[fw] flashing rootfs: " << flashCmd << std::endl;
    int rc = system(flashCmd.c_str());
    if (rc != 0) {
        JsonObj obj;
        obj.pair("ok", JsonValue::boolean(false));
        obj.pair("error", JsonValue::string("flash write failed"));
        resp.body = obj.done();
        resp.send(fd);
        return;
    }

    JsonObj obj;
    obj.pair("ok", JsonValue::boolean(true));
    obj.pair("size", JsonValue::number((int)contentLen));
    obj.pair("message", JsonValue::string("Rootfs updated. Reboot to apply. U-Boot/kernel NOT touched."));
    resp.body = obj.done();
    resp.send(fd);
}

// ═══════════════════════════════════════════════════════════════
// 主函数
// ═══════════════════════════════════════════════════════════════

int main() {
    // 检测 LAN 网口名
    g_lanIface = detectLanIface();
    std::cout << "[web_server] LAN 网口: " << g_lanIface << std::endl;

    // 加载配置 + 应用已有转发规则
    Config cfg = loadConfig();
    saveConfig(cfg);  // 自动检测写入
    applyAllForwards(cfg);

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

    while (true) {
        int cli = accept(srv, nullptr, nullptr);
        if (cli < 0) { if (errno == EINTR) continue; break; }

        // 每个请求一个线程
        std::thread([cli]() {
            // Peek at request line to detect firmware upload
            char peek[64] = {};
            int peekLen = ::recv(cli, peek, sizeof(peek)-1, MSG_PEEK);
            if (peekLen > 0) {
                peek[peekLen] = '\0';
                std::string peekStr(peek);
                if (peekStr.find("POST /api/firmware/upload") != std::string::npos) {
                    handleFirmwareUpload(cli);
                    close(cli);
                    return;
                }
            }

            char buf[BUF_SZ];
            int n = recv(cli, buf, sizeof(buf) - 1, 0);
            if (n > 0) {
                buf[n] = '\0';
                Request req = parseRequest(buf, n);
                Response resp = handleRequest(req);
                resp.send(cli);
            }
            close(cli);
        }).detach();
    }

    close(srv);
    return 0;
}
