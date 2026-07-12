#!/usr/bin/env python3
"""TUN_NAT_HUB Web 配置面板 — 零依赖，纯标准库。"""
import http.server, json, subprocess, urllib.parse, time, os

VERSION = "1.1.0"
PORT = 8080
CFG_FILE = os.path.expanduser("~/tun_nat_hub_config.json")

# 威胁模型: USB 物理连接为安全边界。以下密码仅用于本地 sudo。
# 若 V3s 以 root 运行则跳过 sudo；若以普通用户运行则需 sudoers 或此密码。
_SUDO = [] if os.geteuid() == 0 else ["sudo", "-S"]

def detect_lan_subnet():
    """从 eth0 实际 IP 自动推断 LAN 网段，例如 192.168.144.66/24 → 192.168.144.0/24"""
    try:
        r = subprocess.run(["ip","addr","show","eth0"], capture_output=True, text=True, timeout=5)
        for line in r.stdout.split("\n"):
            stripped = line.strip()
            if stripped.startswith("inet "):
                parts = stripped.split()
                cidr = parts[1]  # 例如 "192.168.144.66/24"
                ip_addr, prefix = cidr.split("/")
                octets = ip_addr.split(".")
                octets[3] = "0"
                subnet = ".".join(octets) + "/" + prefix
                return subnet
    except Exception:
        pass
    return None

def _merge_defaults(cfg):
    defaults = {"rtsp_url":"rtsp://192.168.88.100:554/stream1","lan_subnet":"192.168.88.0/24","tun_subnet":"10.0.0.0/24","forwards":[],"cameras":[{"name":"Camera 1","url":"rtsp://192.168.88.101:554/stream1"}]}
    for k, v in defaults.items():
        if k not in cfg: cfg[k] = v

def load_cfg():
    try:
        with open(CFG_FILE) as f:
            cfg = json.load(f)
        _merge_defaults(cfg)
        # 自动检测: 如果 V3s eth0 实际 IP 的网段与配置不同，自动更新
        detected = detect_lan_subnet()
        if detected and detected != cfg.get("lan_subnet"):
            print(f"[web_panel] LAN 网段自动检测: {cfg.get('lan_subnet')} → {detected}")
            cfg["lan_subnet"] = detected
            save_cfg(cfg)
        return cfg
    except Exception:
        defaults = {"rtsp_url":"rtsp://192.168.88.100:554/stream1","lan_subnet":"192.168.88.0/24","tun_subnet":"10.0.0.0/24","forwards":[],"cameras":[{"name":"Camera 1","url":"rtsp://192.168.88.101:554/stream1"}]}
        # 即使无配置文件，也尝试从 eth0 推断
        detected = detect_lan_subnet()
        if detected:
            defaults["lan_subnet"] = detected
        return defaults

def save_cfg(cfg):
    with open(CFG_FILE, "w") as f: json.dump(cfg, f, indent=2)

def get_stats():
    try:
        # 从 daemon 日志读取统计（兼容 systemd 和 BusyBox init）
        r = subprocess.run(["tail","-1","/var/log/usb_tund.log"], capture_output=True, text=True, timeout=5)
        line = r.stdout.strip()
        res = {"tx_pkts":0,"tx_bytes":0,"rx_pkts":0,"rx_bytes":0,"bandwidth_mbps":"0.0","hb":0,"err":0}
        for p in line.split():
            if "TX=" in p:
                v = p.split("=")[1].split("/")
                res["tx_pkts"] = int(v[0])
                res["tx_bytes"] = int(v[1].replace("B",""))
            elif "RX=" in p:
                v = p.split("=")[1].split("/")
                res["rx_pkts"] = int(v[0])
                res["rx_bytes"] = int(v[1].replace("B",""))
            elif "HB=" in p: res["hb"] = int(p.split("=")[1])
            elif "err=" in p: res["err"] = int(p.split("=")[1])
        # Calculate real-time bandwidth using 2-sample diff
        if hasattr(get_stats, "_prev"):
            elapsed = time.time() - get_stats._prev["time"]
            if elapsed > 0:
                tx_diff = res["tx_bytes"] - get_stats._prev["tx_bytes"]
                mbps = (tx_diff * 8) / (elapsed * 1_000_000)
                res["bandwidth_mbps"] = f"{mbps:.1f}"
        get_stats._prev = {"time": time.time(), "tx_bytes": res["tx_bytes"]}
        return res
    except Exception: return {"tx_pkts":0,"tx_bytes":0,"rx_pkts":0,"rx_bytes":0,"bandwidth_mbps":"0.0","hb":0,"err":0}

def get_system():
    mem = subprocess.run(["free","-m"],capture_output=True,text=True).stdout.split("\n")
    disk = subprocess.run(["df","-h","/"],capture_output=True,text=True).stdout.split("\n")
    uptime = subprocess.run(["cat","/proc/uptime"],capture_output=True,text=True).stdout.strip().split()[0] + "s"
    daemon_active = subprocess.run(["pidof","usb_tund"],capture_output=True).returncode == 0
    web_active = subprocess.run(["pidof","python3"],capture_output=True).returncode == 0
    return {"uptime":uptime,"daemon_active":daemon_active,"web_active":web_active,"mem":mem[1] if len(mem)>1 else "","disk":disk[1] if len(disk)>1 else ""}

def _run_iptables(args, check=True, input_data=None):
    """安全运行 iptables 命令。V3s 上 root 运行跳过 sudo。"""
    cmd = _SUDO + args
    return subprocess.run(cmd, capture_output=True, input=input_data)

def get_iptables():
    nat = _run_iptables(["iptables","-t","nat","-L","PREROUTING","-n"]).stdout.decode()
    fwd = _run_iptables(["iptables","-L","FORWARD","-n"]).stdout.decode()
    return {"nat":nat,"forward":fwd}

def get_network():
    return subprocess.run(["ip","-br","addr"],capture_output=True,text=True).stdout

def _validate_fwd(proto, port, dest):
    """校验端口转发参数，防止 shell 注入"""
    import ipaddress
    if proto not in ("udp","tcp"): return False
    if not isinstance(port, int) or port < 1 or port > 65535: return False
    # dest 可以是 IP 或 IP:port
    ip_part = dest.split(":")[0]
    try:
        ipaddress.ip_address(ip_part)
    except ValueError:
        return False
    return True

def add_forward(cfg, proto, port, dest_ip):
    if not _validate_fwd(proto, port, dest_ip): return False
    dest = f"{dest_ip}:{port}" if ":" not in dest_ip else dest_ip
    lan = LAN_IFACE
    _run_iptables(["iptables","-t","nat","-A","PREROUTING","-i",lan,"-p",proto,"--dport",str(port),"-j","DNAT","--to-destination",dest])
    _run_iptables(["iptables","-A","FORWARD","-i",lan,"-o","tun_hub","-p",proto,"--dport",str(port),"-j","ACCEPT"])
    cfg["forwards"].append({"proto":proto,"port":port,"dest":dest})
    save_cfg(cfg)
    return True

def remove_forward(cfg, port):
    found = next((r for r in cfg["forwards"] if r["port"]==port), None)
    if not found: return False
    p = found["proto"]; pt = str(port); d = found["dest"]
    lan = LAN_IFACE
    _run_iptables(["iptables","-t","nat","-D","PREROUTING","-i",lan,"-p",p,"--dport",pt,"-j","DNAT","--to-destination",d])
    _run_iptables(["iptables","-D","FORWARD","-i",lan,"-o","tun_hub","-p",p,"--dport",pt,"-j","ACCEPT"])
    cfg["forwards"] = [r for r in cfg["forwards"] if r["port"]!=port]
    save_cfg(cfg)
    return True

def detect_lan_iface():
    """自动检测 LAN 网口名称 (eth0 > end1 > end0 > enp*)"""
    import re
    try:
        r = subprocess.run(["ip","addr","show"], capture_output=True, text=True, timeout=5)
        ifaces = re.findall(r'^\d+:\s+(\S+):', r.stdout, re.MULTILINE)
        # 排除 lo/tun/docker/veth 等虚拟接口
        for iface in ifaces:
            if iface in ("lo","tun_hub","tun0","docker0","veth","br-","virbr"): continue
            if iface.startswith(("tun","docker","veth","br","vir")): continue
            # 检查是否有 IPv4 地址
            r2 = subprocess.run(["ip","addr","show",iface], capture_output=True, text=True, timeout=5)
            if "inet " in r2.stdout and "inet 10.0.0." not in r2.stdout:
                return iface
    except Exception: pass
    return "eth0"  # fallback

LAN_IFACE = detect_lan_iface()

def apply_all_forwards(cfg):
    global LAN_IFACE
    lan = LAN_IFACE
    for rule in cfg.get("forwards",[]):
        p = rule["proto"]; pt = str(rule["port"]); d = rule["dest"]
        # -C 检查规则是否存在，不存在才 -A（防止重复）
        check = _run_iptables(["iptables","-t","nat","-C","PREROUTING","-i",lan,"-p",p,"--dport",pt,"-j","DNAT","--to-destination",d])
        if check.returncode != 0:
            _run_iptables(["iptables","-t","nat","-A","PREROUTING","-i",lan,"-p",p,"--dport",pt,"-j","DNAT","--to-destination",d])
        check = _run_iptables(["iptables","-C","FORWARD","-i",lan,"-o","tun_hub","-p",p,"--dport",pt,"-j","ACCEPT"])
        if check.returncode != 0:
            _run_iptables(["iptables","-A","FORWARD","-i",lan,"-o","tun_hub","-p",p,"--dport",pt,"-j","ACCEPT"])

# ══════════════════════════════════════════════════════════
# HTML — 完整中文面板
# ══════════════════════════════════════════════════════════
HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>TUN NAT HUB · 配置面板</title>
<style>
:root{--bg:#0b1121;--card:#111827;--bd:#1e293b;--fg:#e2e8f0;--muted:#94a3b8;--dim:#64748b;--cyan:#38bdf8;--green:#22c55e;--red:#ef4444;--amber:#f59e0b;--blue:#3b82f6}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,"Microsoft YaHei",sans-serif;background:var(--bg);color:var(--fg);min-height:100vh;line-height:1.5}
header{background:var(--card);padding:14px 24px;border-bottom:1px solid var(--bd);display:flex;align-items:center;gap:12px}
header .logo{font-size:1.4em;font-weight:700;background:linear-gradient(135deg,var(--cyan),var(--blue));-webkit-background-clip:text;-webkit-text-fill-color:transparent}
header .ver{font-size:0.7em;color:var(--dim);margin-left:4px}
.page{padding:20px 24px;max-width:1400px;margin:0 auto}
.tabs{display:flex;gap:4px;margin-bottom:20px;border-bottom:2px solid var(--bd);padding-bottom:0}
.tab{padding:10px 20px;cursor:pointer;border-radius:8px 8px 0 0;color:var(--muted);font-size:0.9em;font-weight:500;transition:all .2s}
.tab:hover{color:var(--fg);background:rgba(56,189,248,0.05)}
.tab.active{color:var(--cyan);border-bottom:2px solid var(--cyan);margin-bottom:-2px}
.tab-content{display:none}
.tab-content.active{display:block}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:16px}
.grid3{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}
.card{background:var(--card);border-radius:10px;padding:18px;border:1px solid var(--bd)}
.card h3{font-size:0.95em;color:var(--muted);margin-bottom:14px;padding-bottom:8px;border-bottom:1px solid var(--bd)}
.arch-box{background:#0a0f1a;border:1px solid #1e3a5f;border-radius:10px;padding:20px;margin-bottom:16px;font-family:'Cascadia Code','Consolas',monospace;font-size:0.8em;white-space:pre;overflow-x:auto;line-height:1.6}
.arch{display:flex;flex-direction:column;gap:4px}
.arch .box{display:inline-block;background:rgba(56,189,248,0.1);border:1px solid rgba(56,189,248,0.3);border-radius:4px;padding:2px 8px;margin:1px}
.arch .box2{background:rgba(245,158,11,0.1);border:1px solid rgba(245,158,11,0.3);border-radius:4px;padding:2px 8px;margin:1px}
.arch .box3{background:rgba(34,197,94,0.1);border:1px solid rgba(34,197,94,0.3);border-radius:4px;padding:2px 8px;margin:1px}
.arch .arrow{color:var(--cyan);font-weight:bold}
.arch .label{color:var(--dim);font-size:0.85em}
.stat-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.stat-item{background:var(--bg);border-radius:6px;padding:10px 12px;text-align:center}
.stat-value{font-size:1.6em;font-weight:700;font-family:monospace;color:var(--cyan)}
.stat-value.green{color:var(--green)}
.stat-value.amber{color:var(--amber)}
.stat-label{font-size:0.75em;color:var(--dim);margin-top:2px}
.stat-row{display:flex;justify-content:space-between;padding:3px 0;font-size:0.85em}
.stat-row span:first-child{color:var(--muted)}
.stat-row span:last-child{color:var(--cyan);font-family:monospace}
.meter{height:6px;background:var(--bg);border-radius:3px;margin:4px 0;overflow:hidden}
.meter-fill{height:100%;background:linear-gradient(90deg,var(--cyan),var(--blue));border-radius:3px;transition:width .5s}
.dot{display:inline-block;width:7px;height:7px;border-radius:50%;margin-right:5px}
.dot.on{background:var(--green);box-shadow:0 0 6px var(--green)}
.dot.off{background:var(--red)}
.form-row{display:flex;gap:8px;margin-bottom:8px;align-items:center}
input,select{flex:1;padding:7px 10px;border:1px solid var(--bd);border-radius:6px;background:var(--bg);color:var(--fg);font-size:0.85em}
input:focus,select:focus{outline:none;border-color:var(--cyan)}
.btn{padding:7px 16px;border:none;border-radius:6px;cursor:pointer;font-size:0.85em;font-weight:500;white-space:nowrap;transition:opacity .2s}
.btn:hover{opacity:0.85}
.btn-blue{background:var(--blue);color:#fff}
.btn-red{background:var(--red);color:#fff}
.btn-green{background:var(--green);color:#000}
.btn-sm{padding:3px 10px;font-size:0.75em}
.rules{list-style:none;font-size:0.85em}
.rules li{display:flex;justify-content:space-between;align-items:center;padding:5px 0;border-bottom:1px solid var(--bd)}
.rules li:last-child{border:none}
.code-block{background:var(--bg);padding:12px;border-radius:6px;font-family:monospace;font-size:0.78em;max-height:280px;overflow:auto;white-space:pre}
.help dt{color:var(--cyan);font-weight:600;margin-top:10px}
.help dd{color:var(--muted);font-size:0.9em;margin-left:12px;margin-top:2px}
.help dd code{background:var(--bg);padding:1px 5px;border-radius:3px;color:var(--amber)}
.warn{background:rgba(239,68,68,0.1);border:1px solid rgba(239,68,68,0.3);border-radius:6px;padding:10px 14px;font-size:0.85em;color:var(--red);margin-top:8px}
.info{background:rgba(59,130,246,0.1);border:1px solid rgba(59,130,246,0.3);border-radius:6px;padding:10px 14px;font-size:0.85em;color:var(--blue);margin-top:8px}
@media(max-width:900px){.grid2,.grid3{grid-template-columns:1fr}}
</style>
</head>
<body>
<header>
  <span class="logo">TUN NAT HUB</span><span class="ver">v1.1.0 · g_serial RTL8812AU</span>
  <span style="flex:1"></span>
  <span id="header-status">⏳</span>
</header>

<div class="page">
  <div class="tabs">
    <div class="tab active" onclick="switchTab('overview')">📖 概览与链路</div>
    <div class="tab" onclick="switchTab('config')">⚙️ 配置</div>
    <div class="tab" onclick="switchTab('network')">🌐 网络与防火墙</div>
    <div class="tab" onclick="switchTab('help')">❓ 使用说明</div>
  </div>

  <!-- ═══════ TAB: OVERVIEW ═══════ -->
  <div class="tab-content active" id="tab-overview">
    <div class="grid3" style="margin-bottom:16px">
      <div class="stat-item"><div class="stat-value" id="ov-bw">--</div><div class="stat-label">实时带宽 (Mbps)</div></div>
      <div class="stat-item"><div class="stat-value green" id="ov-tx">--</div><div class="stat-label">累计发送</div></div>
      <div class="stat-item"><div class="stat-value amber" id="ov-rx">--</div><div class="stat-label">累计接收</div></div>
    </div>

    <div class="card" style="margin-bottom:16px">
      <h3>🔗 完整数据链路</h3>
      <div style="display:flex;flex-direction:column;gap:8px;padding:10px 0">
        <!-- Row 1: DJI RC -->
        <div style="display:flex;align-items:stretch;gap:0">
          <div style="flex:1;background:rgba(56,189,248,0.08);border:2px solid rgba(56,189,248,0.4);border-radius:12px;padding:12px 16px">
            <div style="font-weight:700;color:var(--cyan);font-size:0.95em;margin-bottom:6px">📱 DJI RC PLUS 2 · Android 11</div>
            <div style="font-size:0.8em;color:var(--muted);line-height:1.6">
              App 发起请求<br>→ <b>VpnService TUN</b> (<code>10.0.0.2/24</code>)<br>
              → 路由 <code>192.168.88.0/24</code> 进入 TUN<br>
              → <b>UsbBridge.kt</b> (双协程)<br>
              → <code>bulkTransfer()</code> USB Host API<br>
              → 帧打包 <code>[0x544E][Len][IP包]</code><br>
              → <b>EasyPlayer</b> 解码 → SurfaceView
            </div>
          </div>
        </div>

        <!-- Arrow down -->
        <div style="text-align:center;color:var(--cyan);font-size:1.4em;line-height:1">⬇ ⬆<br><span style="font-size:0.55em;color:var(--dim)">USB 2.0 线缆 (Bulk IN/OUT)</span></div>

        <!-- Row 2: RK3588 -->
        <div style="display:flex;align-items:stretch;gap:0">
          <div style="flex:1;background:rgba(245,158,11,0.08);border:2px solid rgba(245,158,11,0.4);border-radius:12px;padding:12px 16px">
            <div style="font-weight:700;color:var(--amber);font-size:0.95em;margin-bottom:6px">🖥 RK3588 · Rock 5C · Ubuntu</div>
            <div style="display:flex;gap:12px">
              <div style="flex:1;font-size:0.8em;color:var(--muted);line-height:1.6">
                <b>USB Gadget</b>: <code>g_serial use_acm=0</code><br>
                VID=<code>0x0BDA</code> PID=<code>0x8812</code><br>
                (伪装 RTL8812AU 过 DJI 白名单)<br>
                → <code>/dev/ttyGS0</code>
              </div>
              <div style="width:2px;background:var(--bd)"></div>
              <div style="flex:1;font-size:0.8em;color:var(--muted);line-height:1.6">
                <b>usb_tund v5</b> (C++ 守护进程)<br>
                → 帧解包 → <code>tun_hub</code><br>
                (<code>10.0.0.1/24</code>)<br>
                → 内核路由 + <b>MASQUERADE</b>
              </div>
            </div>
          </div>
        </div>

        <!-- Arrow down -->
        <div style="text-align:center;color:var(--amber);font-size:1.4em;line-height:1">⬇ ⬆<br><span style="font-size:0.55em;color:var(--dim)">千兆以太网 (end1 · 192.168.88.66)</span></div>

        <!-- Row 3: LAN -->
        <div style="display:flex;gap:12px">
          <div style="flex:1;background:rgba(34,197,94,0.08);border:2px solid rgba(34,197,94,0.4);border-radius:12px;padding:12px 16px">
            <div style="font-weight:700;color:var(--green);font-size:0.95em;margin-bottom:6px">📹 IP Camera</div>
            <div style="font-size:0.8em;color:var(--muted)"><code>192.168.88.100</code><br>RTSP <code>:554/stream1</code></div>
          </div>
          <div style="flex:1;background:rgba(139,92,246,0.08);border:2px solid rgba(139,92,246,0.4);border-radius:12px;padding:12px 16px">
            <div style="font-weight:700;color:#a78bfa;font-size:0.95em;margin-bottom:6px">💻 Windows PC</div>
            <div style="font-size:0.8em;color:var(--muted)"><code>192.168.88.x</code><br>网络助手 / 浏览器</div>
          </div>
        </div>

        <div style="text-align:center;font-size:0.7em;color:var(--dim);margin-top:8px">
          ═══ 交换机 · LAN <code>192.168.88.0/24</code> ═══
        </div>
      </div>

      <div class="info" style="margin-top:12px">
        <b>数据方向:</b><br>
        🟢 <b>出向 (DJI RC → LAN)</b>: App → TUN → USB → RK3588 → MASQ NAT → 交换机 → 目标设备 (自动，无需配置)<br>
        🔵 <b>入向 (LAN → DJI RC)</b>: 需要在「配置」Tab 添加 <b>端口转发</b>，iptables DNAT 到 <code>10.0.0.2</code>
      </div>
    </div>

    <div class="grid2">
      <div class="card"><h3>📦 帧协议格式</h3>
        <div class="code-block" style="text-align:center">
 Byte 0   1    2    3    4 ... N+3
┌──────┬──────┬──────────────┬──────────┐
│ 0x54 │ 0x4E │ Length (BE)  │ Payload  │
│ 'T'  │ 'N'  │  [0 ~ 2048]  │ N bytes  │
└──────┴──────┴──────────────┴──────────┘
 Len=0 → Heartbeat    Len=2 → Credit
        </div></div>
      <div class="card"><h3>🎯 关键参数</h3>
        <div class="stat-row"><span>TUN MTU</span><span>1400</span></div>
        <div class="stat-row"><span>USB 超时 (Android)</span><span>10ms</span></div>
        <div class="stat-row"><span>TTY VTIME</span><span>0 (即时)</span></div>
        <div class="stat-row"><span>心跳间隔</span><span>1000ms</span></div>
        <div class="stat-row"><span>测速结果</span><span>87 Mbps (USB 2.0 Bulk)</span></div>
        <div class="stat-row"><span>核心技术</span><span>VID 伪装过 DJI 白名单</span></div>
        <div class="stat-row"><span>数据通道</span><span>纯 USB 线，不依赖 WiFi</span></div>
      </div>
    </div>
  </div>

  <!-- ═══════ TAB: CONFIG ═══════ -->
  <div class="tab-content" id="tab-config">
    <div class="grid2">
      <div class="card">
        <h3>📹 多路摄像头管理</h3>
        <div style="color:var(--dim);font-size:0.8em;margin-bottom:6px">添加多个摄像头。App 可通过 <code>/api/cameras</code> 获取列表切换源。<br>Web 面板修改后 App 自动同步。</div>
        <div class="form-row">
          <input id="cam-name" type="text" placeholder="名称" style="flex:0;width:100px">
          <input id="cam-url" type="text" placeholder="rtsp://192.168.88.101:554/stream1">
          <button class="btn btn-green" onclick="addCam()">＋ 添加</button>
        </div>
        <ul class="rules" id="cam-list"><li style="color:var(--dim)">加载中...</li></ul>
      </div>

      <div class="card">
        <h3>🔀 端口转发 (外网 → DJI RC)</h3>
        <div style="color:var(--dim);font-size:0.8em;margin-bottom:8px">让 Windows / 局域网设备能主动发数据给 DJI RC</div>
        <div class="form-row">
          <select id="fw-proto" style="flex:0;width:70px"><option value="udp">UDP</option><option value="tcp">TCP</option></select>
          <input id="fw-port" type="number" placeholder="端口" min="1" max="65535" style="flex:0;width:80px">
          <input id="fw-dest" type="text" value="10.0.0.2" style="flex:0;width:110px" placeholder="目标IP">
          <button class="btn btn-green" onclick="addFwd()">＋ 添加</button>
        </div>
        <ul class="rules" id="fwd-list"><li style="color:var(--dim)">加载中...</li></ul>
        <div class="warn" style="margin-top:10px">⚠️ 配了转发后，DJI RC App 里也要监听对应端口才能收到数据。</div>
      </div>
    </div>
  </div>

  <!-- ═══════ TAB: NETWORK ═══════ -->
  <div class="tab-content" id="tab-network">
    <div class="grid2">
      <div class="card">
        <h3>🌐 网口信息</h3>
        <pre class="code-block" id="net-info">加载中...</pre>
      </div>
      <div class="card">
        <h3>🔒 iptables 规则</h3>
        <pre class="code-block" id="ipt-info">加载中...</pre>
      </div>
    </div>
    <div class="grid3" style="margin-top:16px">
      <div class="card"><h3>🖥 系统信息</h3>
        <div id="sys-info">加载中...</div>
      </div>
      <div class="card"><h3>📊 流量累计</h3>
        <div id="stats-detail">加载中...</div>
      </div>
      <div class="card"><h3>💾 资源</h3>
        <div id="res-info">加载中...</div>
      </div>
    </div>
  </div>

  <!-- ═══════ TAB: HELP ═══════ -->
  <div class="tab-content" id="tab-help">
    <div class="card">
      <h3>❓ 项目说明与使用方法</h3>
      <dl class="help">
        <dt>这个项目干什么的？</dt>
        <dd>让 <b>DJI RC PLUS 2</b> 遥控器通过 <b>USB 线</b> 连接到 <b>RK3588</b> 盒子，RK3588 再通过网线接入局域网。DJI RC 就能访问局域网里的 IP 摄像头、电脑等设备。数据<b>不经过 WiFi</b>，纯 USB 传输。</dd>

        <dt>为什么不用 WiFi？</dt>
        <dd>DJI RC 遥控器正常情况下<b>没有 WiFi</b>。即使有，DJI 也对 USB 设备做了白名单限制，非授权设备插上无法通信。本项目通过<b>伪装 RTL8812AU WiFi 芯片的 VID/PID</b> 绕过了这个限制。</dd>

        <dt>IP 地址怎么规划的？</dt>
        <dd>
          DJI RC VPN (TUN): <code>10.0.0.2</code><br>
          RK3588 TUN: <code>10.0.0.1</code><br>
          RK3588 LAN: <code>192.168.88.66</code>（DHCP 自动获取）<br>
          USB 内部网段: <code>10.0.0.0/24</code>（点对点隧道）<br>
          局域网: <code>192.168.88.0/24</code>
        </dd>

        <dt>DJI RC 怎么访问局域网设备？</dt>
        <dd>DJI RC → App VPN → USB 隧道 → RK3588 → NAT 伪装 → 局域网。反过来，局域网设备要访问 DJI RC 需要配<b>端口转发</b>，在「配置」Tab 里操作。</dd>

        <dt>Windows 网络助手怎么发 UDP 到 DJI RC？</dt>
        <dd>
          1. 在「配置」Tab 添加端口转发，比如 UDP 5000 → 10.0.0.2<br>
          2. 网络助手目标地址填 <code>192.168.88.66:5000</code><br>
          3. DJI RC App 监听 <code>5000</code> 端口接收<br>
          ⚠️ 不是填 10.0.0.2，那个是内部隧道地址，局域网机器看不到！
        </dd>

        <dt>怎么在 DJI RC App 里收 UDP 数据？</dt>
        <dd>
          在 Kotlin 里创建 DatagramSocket，<b>必须调用 VpnService.protect(socket)</b> 防止被 VPN 吞掉：<br>
          <code>val s = DatagramSocket(5000)</code><br>
          <code>VpnService.protect(s)</code><br>
          <code>s.receive(packet)</code>
        </dd>

        <dt>怎么改 RTSP 摄像头地址？</dt>
        <dd>在「配置」Tab 修改后保存。App 重启后生效。</dd>

        <dt>视频有延迟怎么办？</dt>
        <dd>
          USB 隧道本身延迟 ~1-3ms。延迟主要来自：<br>
          1. 摄像头 H.264 编码 (~30-80ms)<br>
          2. 播放器缓冲 (EasyPlayer 已从默认 1000ms 降到 50ms)<br>
          3. 可以考虑用 UDP 裸流替代 RTSP/TCP
        </dd>

        <dt>服务怎么管理？</dt>
        <dd>
          <code>ps | grep usb_tund</code> — USB 隧道守护进程<br>
          <code>ps | grep web_panel</code> — 本 Web 面板<br>
          <code>journalctl -u tun_nat_hub -f</code> — 实时日志
        </dd>

        <dt>SSH 连不上 RK3588 怎么办？</dt>
        <dd>
          RK3588 地址: <code>192.168.88.66</code>（或当前的 DHCP 地址）<br>
          用户名: <code>xlong</code> 密码: <code>1234</code><br>
          Windows 上可以用 PuTTY 或 plink 连接。
        </dd>
      </dl>
    </div>
  </div>
</div>

<script>
const API = "/api";
async function getJ(url){try{const r=await fetch(url);return r.json()}catch(e){return{}}}
async function getT(url){try{const r=await fetch(url);return r.text()}catch(e){return"加载失败"}}

function switchTab(name) {
  document.querySelectorAll(".tab").forEach(t=>t.classList.remove("active"));
  document.querySelectorAll(".tab-content").forEach(c=>c.classList.remove("active"));
  document.querySelector(`.tab[onclick*="${name}"]`).classList.add("active");
  document.getElementById("tab-"+name).classList.add("active");
}

async function fetchHb(){
  try{const r=await fetch(API+"/heartbeat");const h=await r.json();
  document.getElementById("hb-daemon").innerHTML=h.daemon?"✅ 运行":"❌ 停止";
  document.getElementById("hb-daemon").style.color=h.daemon?"var(--green)":"var(--red)";
  document.getElementById("hb-tty").innerHTML=h.tty_ready?"✅ 就绪":"❌ 未检测";
  document.getElementById("hb-tty").style.color=h.tty_ready?"var(--green)":"var(--red)";
  document.getElementById("hb-tun").innerHTML=h.tun_up?"✅ UP":"❌ DOWN";
  document.getElementById("hb-tun").style.color=h.tun_up?"var(--green)":"var(--red)";
  document.getElementById("hb-time").innerHTML=h.uptime_since||"--";
  }catch(e){}
}
async function refresh() {
  const sys = await getJ(API+"/system");
  const st = await getJ(API+"/stats");
  const cfg = await getJ(API+"/config");

  // Header
  const d = sys.daemon_active;
  document.getElementById("header-status").innerHTML =
    `<span class="dot ${d?'on':'off'}"></span>守护进程: ${d?'运行中':'已停止'} | ` +
    `<span class="dot ${sys.web_active?'on':'off'}"></span>Web: ${sys.web_active?'运行中':'已停止'}`;

  // Overview tab
  document.getElementById("ov-bw").textContent = st.bandwidth_mbps||"0.0";
  document.getElementById("ov-tx").textContent = (st.tx_bytes/1024/1024).toFixed(1)+" MB";
  document.getElementById("ov-rx").textContent = (st.rx_bytes/1024/1024).toFixed(1)+" MB";

  // Config tab
  document.getElementById("rtsp-url").value = cfg.rtsp_url||"";
  // Camera list
  let cl = "";
  if (cfg.cameras && cfg.cameras.length>0) {
    cfg.cameras.forEach((c,i)=>{cl+=`<li><span>${c.name}: ${c.url}</span><button class="btn btn-red btn-sm" onclick="delCam(${i})">删除</button></li>`});
  } else {cl="<li style='color:var(--dim)'>暂无摄像头，请添加</li>";}
  document.getElementById("cam-list").innerHTML = cl;
  let fl = "";
  if (cfg.forwards && cfg.forwards.length>0) {
    cfg.forwards.forEach(f=>{fl+=`<li><span>${f.proto.toUpperCase()} :${f.port} → ${f.dest}</span><button class="btn btn-red btn-sm" onclick="delFwd(${f.port})">删除</button></li>`});
  } else {fl="<li style='color:var(--dim)'>暂无转发规则</li>";}
  document.getElementById("fwd-list").innerHTML = fl;

  // Network tab
  document.getElementById("net-info").textContent = await getT(API+"/network");
  document.getElementById("ipt-info").textContent = await getT(API+"/iptables");
  document.getElementById("sys-info").innerHTML =
    `<div class="stat-row"><span>运行时间</span><span>${sys.uptime||'N/A'}</span></div>`+
    `<div class="stat-row"><span>守护进程</span><span>${d?'✅ 运行中':'❌ 已停止'}</span></div>`+
    `<div class="stat-row"><span>Web 面板</span><span>${sys.web_active?'✅ 运行中':'❌ 已停止'}</span></div>`;
  document.getElementById("stats-detail").innerHTML =
    `<div class="stat-row"><span>TX 包数</span><span>${st.tx_pkts||0}</span></div>`+
    `<div class="stat-row"><span>TX 数据量</span><span>${(st.tx_bytes/1024/1024).toFixed(1)} MB</span></div>`+
    `<div class="stat-row"><span>RX 包数</span><span>${st.rx_pkts||0}</span></div>`+
    `<div class="stat-row"><span>RX 数据量</span><span>${(st.rx_bytes/1024/1024).toFixed(1)} MB</span></div>`+
    `<div class="stat-row"><span>心跳包</span><span>${st.hb||0}</span></div>`+
    `<div class="stat-row"><span>错误</span><span>${st.err||0}</span></div>`;
  document.getElementById("res-info").innerHTML =
    `<div class="stat-row"><span>内存</span><span>${(sys.mem||'').split(' ').filter(x=>x).slice(1,4).join(' ')}</span></div>`+
    `<div class="stat-row"><span>磁盘</span><span>${(sys.disk||'').split(' ').filter(x=>x).slice(1,5).join(' ')}</span></div>`;
}

async function addFwd(){
  const proto=document.getElementById("fw-proto").value;
  const port=parseInt(document.getElementById("fw-port").value);
  const dest=document.getElementById("fw-dest").value;
  if(!port||port<1||port>65535){alert("端口无效");return}
  const r=await fetch(API+"/forward/add",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({proto,port,dest})});
  if(r.ok) refresh(); else alert("添加失败");
}
async function delFwd(port){
  const r=await fetch(API+"/forward/del",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({port})});
  if(r.ok) refresh(); else alert("删除失败");
}
async function saveRtsp(){
  const url=document.getElementById("rtsp-url").value;
  await fetch(API+"/config/save",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({rtsp_url:url})});
  alert("已保存!");
}
async function addCam(){
  const name=document.getElementById("cam-name").value||"Camera";
  const url=document.getElementById("cam-url").value;
  if(!url){alert("请输入 RTSP 地址");return}
  const r=await fetch(API+"/camera/add",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({name,url})});
  if(r.ok){document.getElementById("cam-name").value="";document.getElementById("cam-url").value="";refresh();}else alert("添加失败");}
async function delCam(idx){
  const r=await fetch(API+"/camera/del",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({index:idx})});
  if(r.ok) refresh();else alert("删除失败");}
fetchHb();refresh();setInterval(refresh,2000);setInterval(fetchHb,5000);
</script>
</body></html>"""

# ── 心跳状态（供 App 轮询） ───────────────────────────────────
_hb_prev = {"time": 0, "tx": 0, "rx": 0}

def _read_sysfs_int(path):
    try:
        with open(path) as f:
            return int(f.read().strip())
    except Exception:
        return 0

def get_heartbeat():
    daemon = subprocess.run(["pidof","usb_tund"],capture_output=True).returncode == 0
    tty = subprocess.run(["test","-c","/dev/ttyGS0"],capture_output=True).returncode == 0
    tun = subprocess.run("ip addr show tun_hub 2>/dev/null|grep -q 'inet '",shell=True,capture_output=True).returncode == 0
    usb_vid = _read_sysfs_int("/sys/module/g_serial/parameters/idVendor") if tty else 0

    # 从 /proc/uptime 读取运行时间（无需 awk 依赖）
    try:
        with open("/proc/uptime") as f:
            uptime = f.read().split()[0] + "s"
    except Exception:
        uptime = "0s"

    # 从内核 TUN 统计读取实时带宽（而非 daemon 日志，日志 5s 才更新一次）
    tx_bytes = 0; rx_bytes = 0; bandwidth = "0.0"
    try:
        tx_bytes = _read_sysfs_int("/sys/class/net/tun_hub/statistics/tx_bytes")
        rx_bytes = _read_sysfs_int("/sys/class/net/tun_hub/statistics/rx_bytes")
        global _hb_prev
        now = time.time()
        if _hb_prev["time"] > 0:
            elapsed = now - _hb_prev["time"]
            if elapsed > 0:
                tx_diff = tx_bytes - _hb_prev["tx"]
                rx_diff = rx_bytes - _hb_prev["rx"]
                # 使用 TX+RX 总和计算双向带宽
                mbps = ((tx_diff + rx_diff) * 8) / (elapsed * 1_000_000)
                bandwidth = f"{mbps:.1f}"
        _hb_prev = {"time": now, "tx": tx_bytes, "rx": rx_bytes}
    except Exception:
        pass

    return {
        "version": VERSION,
        "daemon": daemon,
        "tty_ready": tty,
        "tun_up": tun,
        "usb_vid": usb_vid,
        "usb_pid": _read_sysfs_int("/sys/module/g_serial/parameters/idProduct") if tty else 0,
        "timestamp": int(time.time()),
        "uptime_since": uptime,
        "tx_bytes": tx_bytes,
        "rx_bytes": rx_bytes,
        "bandwidth_mbps": bandwidth,
    }

# ══════════════════════════════════════════════════════════
# HTTP Handler
# ══════════════════════════════════════════════════════════
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def _json(self, d):
        self.send_response(200); self.send_header("Content-Type","application/json"); self.send_header("Access-Control-Allow-Origin","*"); self.end_headers()
        self.wfile.write(json.dumps(d).encode())
    def _text(self, t):
        self.send_response(200); self.send_header("Content-Type","text/plain; charset=utf-8"); self.send_header("Access-Control-Allow-Origin","*"); self.end_headers()
        self.wfile.write(t.encode())
    def do_GET(self):
        p = urllib.parse.urlparse(self.path).path
        if p in ("/","/index.html"):
            self.send_response(200); self.send_header("Content-Type","text/html; charset=utf-8"); self.end_headers()
            self.wfile.write(HTML.encode())
        elif p == "/api/version": self._json({"version":VERSION})
        elif p == "/api/heartbeat": self._json(get_heartbeat())
        elif p == "/api/system": self._json(get_system())
        elif p == "/api/stats": self._json(get_stats())
        elif p == "/api/config": self._json(load_cfg())
        elif p == "/api/network": self._text(get_network())
        elif p == "/api/iptables":
            rules = get_iptables()
            self._text(f"=== NAT PREROUTING ===\n{rules['nat']}\n=== FORWARD ===\n{rules['forward']}")
        else: self.send_response(404); self.end_headers()
    def do_POST(self):
        p = urllib.parse.urlparse(self.path).path
        length = int(self.headers.get("Content-Length",0))
        try:
            body = json.loads(self.rfile.read(length)) if length > 0 else {}
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.send_response(400); self.end_headers(); return
        if p == "/api/forward/add":
            cfg = load_cfg()
            ok = add_forward(cfg, body.get("proto","udp"), body.get("port"), body.get("dest","10.0.0.2"))
            self._json({"ok":ok})
        elif p == "/api/forward/del":
            ok = remove_forward(load_cfg(), body.get("port"))
            self._json({"ok":ok})
        elif p == "/api/config/save":
            cfg = load_cfg()
            if "rtsp_url" in body: cfg["rtsp_url"] = body["rtsp_url"]
            if "cameras" in body: cfg["cameras"] = body["cameras"]
            if "lan_subnet" in body:
                # App 改了 LAN 网段 → 同步改 V3s eth0 IP
                # 格式: "192.168.144.0/24" → V3s IP = "192.168.144.66"
                from ipaddress import ip_network
                try:
                    net = ip_network(body["lan_subnet"], strict=False)
                    v3s_ip = str(net.network_address + 66)  # x.x.x.66
                    new_cidr = body["lan_subnet"]
                    # 更新 /etc/network/interfaces
                    subprocess.run(["sed","-i",f"s/address .*/address {v3s_ip}/","/etc/network/interfaces"])
                    subprocess.run(["sed","-i",f"s/netmask .*/netmask {net.netmask}/","/etc/network/interfaces"])
                    # 立即生效
                    subprocess.run(["ip","addr","flush","dev","eth0"])
                    subprocess.run(["ip","addr","add",new_cidr.replace("0/",f"{v3s_ip.split('.')[-1]}/"),"dev","eth0"])
                    subprocess.run(["ip","link","set","eth0","up"])
                    cfg["lan_subnet"] = new_cidr
                except Exception:
                    pass
            save_cfg(cfg); self._json({"ok":True})
        elif p == "/api/camera/add":
            cfg = load_cfg()
            cfg["cameras"].append({"name":body.get("name","Camera"),"url":body.get("url","")})
            save_cfg(cfg); self._json({"ok":True})
        elif p == "/api/camera/del":
            cfg = load_cfg()
            idx = body.get("index",-1)
            if 0 <= idx < len(cfg["cameras"]):
                cfg["cameras"].pop(idx)
                save_cfg(cfg); self._json({"ok":True})
            else: self._json({"ok":False})
        else: self.send_response(404); self.end_headers()
    def do_OPTIONS(self):
        self.send_response(200); self.send_header("Access-Control-Allow-Origin","*"); self.send_header("Access-Control-Allow-Methods","GET, POST, OPTIONS"); self.send_header("Access-Control-Allow-Headers","Content-Type"); self.end_headers()

def main():
    apply_all_forwards(load_cfg())
    srv = http.server.HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Web panel: http://0.0.0.0:{PORT}")
    print(f"LAN access: http://192.168.88.66:{PORT}")
    try: srv.serve_forever()
    except KeyboardInterrupt: srv.shutdown()

if __name__ == "__main__": main()
