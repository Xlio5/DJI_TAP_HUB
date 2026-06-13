#!/usr/bin/env python3
"""TUN_NAT_HUB Web Config Panel — zero dependencies (stdlib only)."""
import http.server
import json
import os
import subprocess
import sys
import threading
import time
import urllib.parse

PORT = 8080
CFG_FILE = "/home/xlong/tun_nat_hub_config.json"

# ── Configuration Store ────────────────────────────
def load_cfg():
    defaults = {
        "rtsp_url": "rtsp://192.168.88.100:554/stream1",
        "lan_subnet": "192.168.88.0/24",
        "tun_subnet": "10.0.0.0/24",
        "forwards": []  # [{proto:"udp", port:5000, dest:"10.0.0.2"}]
    }
    try:
        with open(CFG_FILE) as f:
            cfg = json.load(f)
        for k, v in defaults.items():
            if k not in cfg:
                cfg[k] = v
        return cfg
    except (FileNotFoundError, json.JSONDecodeError):
        return defaults

def save_cfg(cfg):
    with open(CFG_FILE, "w") as f:
        json.dump(cfg, f, indent=2)

# ── System Info ─────────────────────────────────────
def get_stats():
    """Read daemon stats from journalctl."""
    try:
        r = subprocess.run(
            ["journalctl", "-u", "tun_nat_hub", "--no-pager", "-n", "1", "-o", "cat"],
            capture_output=True, text=True, timeout=5
        )
        line = r.stdout.strip()
        # Parse: [stats] TX=123/456B RX=789/012B HB=3 err=0
        result = {"tx_pkts": 0, "tx_bytes": 0, "rx_pkts": 0, "rx_bytes": 0}
        if "TX=" in line and "RX=" in line:
            parts = line.split()
            for p in parts:
                if "TX=" in p:
                    v = p.split("=")[1]
                    result["tx_pkts"] = int(v.split("/")[0])
                    result["tx_bytes"] = int(v.split("/")[1].replace("B", ""))
                if "RX=" in p:
                    v = p.split("=")[1]
                    result["rx_pkts"] = int(v.split("/")[0])
                    result["rx_bytes"] = int(v.split("/")[1].replace("B", ""))
        return result
    except Exception:
        return {"tx_pkts": 0, "tx_bytes": 0, "rx_pkts": 0, "rx_bytes": 0}

def get_system():
    """Get system info."""
    mem = subprocess.run(["free", "-m"], capture_output=True, text=True).stdout.split("\n")
    disk = subprocess.run(["df", "-h", "/"], capture_output=True, text=True).stdout.split("\n")
    uptime = subprocess.run(["uptime", "-p"], capture_output=True, text=True).stdout.strip()

    daemon_active = False
    r = subprocess.run(["systemctl", "is-active", "tun_nat_hub"], capture_output=True, text=True)
    daemon_active = "active" in r.stdout

    return {
        "uptime": uptime,
        "daemon_active": daemon_active,
        "mem": mem[1] if len(mem) > 1 else "N/A",
        "disk": disk[1] if len(disk) > 1 else "N/A"
    }

def get_iptables():
    """Get current NAT and FORWARD rules."""
    nat = subprocess.run(
        "echo '1234' | sudo -S iptables -t nat -L PREROUTING -n 2>/dev/null",
        shell=True, capture_output=True, text=True
    ).stdout
    fwd = subprocess.run(
        "echo '1234' | sudo -S iptables -L FORWARD -n 2>/dev/null",
        shell=True, capture_output=True, text=True
    ).stdout
    return {"nat": nat, "forward": fwd}

def get_network():
    """Get network interface info."""
    r = subprocess.run(["ip", "-br", "addr"], capture_output=True, text=True)
    return r.stdout

# ── Actions ──────────────────────────────────────────
def add_forward(cfg, proto, port, dest_ip):
    """Add a port forwarding rule."""
    dest = f"{dest_ip}:{port}" if ":" not in dest_ip else dest_ip
    dport = port

    # iptables DNAT
    subprocess.run(
        f"echo '1234' | sudo -S iptables -t nat -A PREROUTING -i end1 -p {proto} --dport {dport} -j DNAT --to-destination {dest}",
        shell=True, capture_output=True
    )
    subprocess.run(
        f"echo '1234' | sudo -S iptables -A FORWARD -i end1 -o tun_hub -p {proto} --dport {dport} -j ACCEPT",
        shell=True, capture_output=True
    )

    # Save to config
    rule = {"proto": proto, "port": dport, "dest": dest}
    cfg["forwards"].append(rule)
    save_cfg(cfg)
    return True

def remove_forward(cfg, port):
    """Remove a port forwarding rule."""
    found = None
    for r in cfg["forwards"]:
        if r["port"] == port:
            found = r
            break
    if not found:
        return False

    proto, dport, dest = found["proto"], found["port"], found["dest"]
    subprocess.run(
        f"echo '1234' | sudo -S iptables -t nat -D PREROUTING -i end1 -p {proto} --dport {dport} -j DNAT --to-destination {dest}",
        shell=True, capture_output=True
    )
    subprocess.run(
        f"echo '1234' | sudo -S iptables -D FORWARD -i end1 -o tun_hub -p {proto} --dport {dport} -j ACCEPT",
        shell=True, capture_output=True
    )

    cfg["forwards"] = [r for r in cfg["forwards"] if r["port"] != port]
    save_cfg(cfg)
    return True

def apply_all_forwards(cfg):
    """Re-apply all saved forwarding rules (after reboot)."""
    for rule in cfg.get("forwards", []):
        subprocess.run(
            f"echo '1234' | sudo -S iptables -t nat -C PREROUTING -i end1 -p {rule['proto']} --dport {rule['port']} -j DNAT --to-destination {rule['dest']} 2>/dev/null || "
            f"echo '1234' | sudo -S iptables -t nat -A PREROUTING -i end1 -p {rule['proto']} --dport {rule['port']} -j DNAT --to-destination {rule['dest']}",
            shell=True, capture_output=True
        )
        subprocess.run(
            f"echo '1234' | sudo -S iptables -C FORWARD -i end1 -o tun_hub -p {rule['proto']} --dport {rule['port']} -j ACCEPT 2>/dev/null || "
            f"echo '1234' | sudo -S iptables -A FORWARD -i end1 -o tun_hub -p {rule['proto']} --dport {rule['port']} -j ACCEPT",
            shell=True, capture_output=True
        )

# ── HTML Frontend ────────────────────────────────────
HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>TUN NAT Hub - Config Panel</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:system-ui,sans-serif;background:#0f172a;color:#e2e8f0;min-height:100vh}
header{background:#1e293b;padding:16px 20px;border-bottom:1px solid #334155}
header h1{font-size:1.2em;color:#38bdf8}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:16px;padding:16px}
.card{background:#1e293b;border-radius:8px;padding:16px;border:1px solid #334155}
.card h2{font-size:1em;color:#94a3b8;margin-bottom:12px;border-bottom:1px solid #334155;padding-bottom:8px}
.stat-row{display:flex;justify-content:space-between;padding:4px 0;font-size:0.9em}
.stat-row span:last-child{color:#38bdf8;font-family:monospace}
.status-dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:6px}
.status-active{background:#22c55e}
.status-inactive{background:#ef4444}
.btn{padding:6px 14px;border:none;border-radius:4px;cursor:pointer;font-size:0.85em}
.btn-blue{background:#2563eb;color:white}
.btn-red{background:#dc2626;color:white}
.btn-green{background:#16a34a;color:white}
.btn:hover{opacity:0.8}
input,select{padding:6px 8px;border:1px solid #475569;border-radius:4px;background:#0f172a;color:#e2e8f0;font-size:0.85em}
.form-row{display:flex;gap:8px;margin-bottom:8px;align-items:center}
.rules-list{list-style:none;font-size:0.85em}
.rules-list li{display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid #334155}
.rules-list li:last-child{border:none}
pre{background:#0f172a;padding:10px;border-radius:4px;font-size:0.75em;max-height:200px;overflow:auto}
.loading{animation:pulse 1s infinite} @keyframes pulse{0%,100%{opacity:1}50%{opacity:0.5}}
</style>
</head>
<body>
<header>
  <h1>🎛 TUN NAT Hub · Config Panel</h1>
</header>

<div class="grid">
  <!-- Dashboard -->
  <div class="card">
    <h2>📊 Daemon Status</h2>
    <div id="sys-info"><span class="loading">Loading...</span></div>
    <div id="stats-info" style="margin-top:8px"></div>
  </div>

  <!-- Port Forwarding -->
  <div class="card">
    <h2>🔀 Port Forwarding (Windows → DJI RC)</h2>
    <div class="form-row">
      <select id="fw-proto"><option value="udp">UDP</option><option value="tcp">TCP</option></select>
      <input id="fw-port" type="number" placeholder="Port" min="1" max="65535" style="width:80px">
      <input id="fw-dest" type="text" placeholder="10.0.0.2" value="10.0.0.2" style="width:100px">
      <button class="btn btn-blue" onclick="addFwd()">Add</button>
    </div>
    <ul class="rules-list" id="fwd-list"><li>Loading...</li></ul>
  </div>

  <!-- RTSP Config -->
  <div class="card">
    <h2>📹 RTSP Stream</h2>
    <div class="form-row">
      <input id="rtsp-url" type="text" placeholder="rtsp://192.168.88.100:554/stream1" style="flex:1">
      <button class="btn btn-blue" onclick="saveRtsp()">Save</button>
    </div>
    <div style="font-size:0.8em;color:#94a3b8;margin-top:8px">Addr: 192.168.88.66 (RK3588 LAN)</div>
  </div>

  <!-- Network Info -->
  <div class="card">
    <h2>🌐 Network Interfaces</h2>
    <pre id="net-info">Loading...</pre>
  </div>

  <!-- iptables -->
  <div class="card">
    <h2>🔒 Firewall Rules</h2>
    <pre id="ipt-info">Loading...</pre>
  </div>
</div>

<script>
const API = "/api";
async function fetchJSON(url) { try { const r = await fetch(url); return r.json(); } catch(e) { return {}; } }
async function fetchText(url) { try { const r = await fetch(url); return r.text(); } catch(e) { return "Error"; } }

async function refresh() {
  // System
  const sys = await fetchJSON(API + "/system");
  document.getElementById("sys-info").innerHTML = `
    <div class="stat-row"><span>Uptime</span><span>${sys.uptime||'N/A'}</span></div>
    <div class="stat-row"><span>Daemon</span><span><span class="status-dot ${sys.daemon_active?'status-active':'status-inactive'}"></span>${sys.daemon_active?'Running':'Stopped'}</span></div>
    <div class="stat-row"><span>Memory</span><span>${sys.mem||'N/A'}</span></div>
    <div class="stat-row"><span>Disk</span><span>${sys.disk||'N/A'}</span></div>
  `;

  // Stats
  const st = await fetchJSON(API + "/stats");
  const tx_mb = (st.tx_bytes / 1024 / 1024).toFixed(1);
  const rx_mb = (st.rx_bytes / 1024 / 1024).toFixed(1);
  document.getElementById("stats-info").innerHTML = `
    <div class="stat-row"><span>TX Packets</span><span>${st.tx_pkts||0}</span></div>
    <div class="stat-row"><span>TX Data</span><span>${tx_mb} MB</span></div>
    <div class="stat-row"><span>RX Packets</span><span>${st.rx_pkts||0}</span></div>
    <div class="stat-row"><span>RX Data</span><span>${rx_mb} MB</span></div>
  `;

  // Config
  const cfg = await fetchJSON(API + "/config");
  document.getElementById("rtsp-url").value = cfg.rtsp_url || "";
  document.getElementById("fw-dest").value = "10.0.0.2";

  // Forwarding rules
  let fhtml = "";
  if (cfg.forwards && cfg.forwards.length > 0) {
    cfg.forwards.forEach(f => {
      fhtml += `<li><span>${f.proto.toUpperCase()} :${f.port} → ${f.dest}</span>
        <button class="btn btn-red" style="padding:2px 8px;font-size:0.75em" onclick="delFwd(${f.port})">X</button></li>`;
    });
  } else {
    fhtml = "<li style='color:#64748b'>No forwarding rules</li>";
  }
  document.getElementById("fwd-list").innerHTML = fhtml;

  // Network
  document.getElementById("net-info").textContent = await fetchText(API + "/network");
  document.getElementById("ipt-info").textContent = await fetchText(API + "/iptables");
}

async function addFwd() {
  const proto = document.getElementById("fw-proto").value;
  const port = parseInt(document.getElementById("fw-port").value);
  const dest = document.getElementById("fw-dest").value;
  if (!port || port < 1 || port > 65535) { alert("Invalid port"); return; }
  const r = await fetch(API + "/forward/add", { method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({proto, port, dest})
  });
  if (r.ok) refresh(); else alert("Failed to add rule");
}

async function delFwd(port) {
  const r = await fetch(API + "/forward/del", { method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({port})
  });
  if (r.ok) refresh(); else alert("Failed to remove rule");
}

async function saveRtsp() {
  const url = document.getElementById("rtsp-url").value;
  await fetch(API + "/config/save", { method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({rtsp_url: url})
  });
  alert("Saved!");
}

refresh();
setInterval(refresh, 3000);
</script>
</body>
</html>"""

# ── HTTP Handler ─────────────────────────────────────
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass  # suppress logs

    def _send_json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def _send_text(self, text):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(text.encode())

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path

        if path == "/" or path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML.encode())
        elif path == "/api/system":
            self._send_json(get_system())
        elif path == "/api/stats":
            self._send_json(get_stats())
        elif path == "/api/config":
            self._send_json(load_cfg())
        elif path == "/api/network":
            self._send_text(get_network())
        elif path == "/api/iptables":
            rules = get_iptables()
            self._send_text(f"=== NAT PREROUTING ===\n{rules['nat']}\n=== FORWARD ===\n{rules['forward']}")
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        path = urllib.parse.urlparse(self.path).path
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length > 0 else {}

        if path == "/api/forward/add":
            cfg = load_cfg()
            ok = add_forward(cfg, body.get("proto", "udp"), body.get("port"), body.get("dest", "10.0.0.2"))
            self._send_json({"ok": ok})
        elif path == "/api/forward/del":
            cfg = load_cfg()
            ok = remove_forward(cfg, body.get("port"))
            self._send_json({"ok": ok})
        elif path == "/api/config/save":
            cfg = load_cfg()
            if "rtsp_url" in body:
                cfg["rtsp_url"] = body["rtsp_url"]
            save_cfg(cfg)
            self._send_json({"ok": True})
        else:
            self.send_response(404)
            self.end_headers()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

# ── Main ──────────────────────────────────────────────
def main():
    # Apply saved forwarding rules on startup
    cfg = load_cfg()
    apply_all_forwards(cfg)

    server = http.server.HTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Web panel running at http://0.0.0.0:{PORT}")
    print(f"Access from LAN: http://192.168.88.66:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()

if __name__ == "__main__":
    main()
