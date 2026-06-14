"""Quick deploy master branch daemon + scripts to RK3588."""
import paramiko, base64, time, os

HOST = "192.168.88.66"
LOCAL_BASE = r"c:\my_project\TUN_NAT_HUB"

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username="xlong", password="1234", timeout=15)

def chan_upload(remote_path, data):
    b64 = base64.b64encode(data).decode()
    chan = c.get_transport().open_session()
    chan.exec_command("base64 -d > " + remote_path)
    chan.sendall(b64.encode())
    chan.shutdown_write()
    return chan.recv_exit_status() == 0

def read_clean(path):
    with open(path, "rb") as f:
        data = f.read()
    return data.replace(b"\r\n", b"\n").replace(b"\r", b"")

def ssh(cmd, timeout=15):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace").strip()
    if out: print(out)
    err = stderr.read().decode(errors="replace").strip()
    if err:
        for line in err.split("\n"):
            if "password" not in line.lower():
                print("E:", line[:200])

def sudossh(cmd, timeout=15):
    stdin, stdout, stderr = c.exec_command(
        "echo 1234 | sudo -S bash -c '" + cmd.replace("'", "'\"'\"'") + "' 2>&1",
        timeout=timeout, get_pty=True)
    out = b""
    import time
    while not stdout.channel.exit_status_ready():
        if stdout.channel.recv_ready():
            out += stdout.channel.recv(4096)
        time.sleep(0.1)
    out += stdout.read()
    text = out.decode(errors="replace")
    for line in text.split("\n"):
        line = line.strip()
        if line and "password" not in line.lower():
            print(line)

# ── Stop ──
print("=== Stop services ===")
sudossh("systemctl stop tun_nat_hub 2>&1 || true")
ssh("killall -9 python3 usb_tund 2>/dev/null; true")
time.sleep(1)

# ── Upload master source ──
print()
print("=== Upload master source ===")
ssh("mkdir -p /home/xlong/tun_master/src /home/xlong/tun_master/protocol /home/xlong/protocol")

srcs = {
    "ubuntu/src/main.cpp": "/home/xlong/tun_master/src/main.cpp",
    "ubuntu/src/tun_iface.cpp": "/home/xlong/tun_master/src/tun_iface.cpp",
    "ubuntu/src/tun_iface.h": "/home/xlong/tun_master/src/tun_iface.h",
    "ubuntu/CMakeLists.txt": "/home/xlong/tun_master/CMakeLists.txt",
    "protocol/frame.h": "/home/xlong/tun_master/protocol/frame.h",
}
for local_rel, remote in srcs.items():
    data = read_clean(os.path.join(LOCAL_BASE, local_rel)).rstrip(b"\n") + b"\n"
    ok = chan_upload(remote, data)
    print("  {} {}".format(os.path.basename(local_rel), "OK" if ok else "FAIL"))

# Link frame.h
ssh("cp /home/xlong/tun_master/protocol/frame.h /home/xlong/protocol/frame.h")

# ── Build ──
print()
print("=== Build ===")
ssh("cd /home/xlong/tun_master && export TMPDIR=/home/xlong/tmp && cmake -B build -DCMAKE_BUILD_TYPE=Release 2>&1", timeout=30)
ssh("cd /home/xlong/tun_master && export TMPDIR=/home/xlong/tmp && cmake --build build 2>&1", timeout=30)

# ── Deploy ──
print()
print("=== Deploy binary ===")
sudossh("cp /home/xlong/tun_master/build/usb_tund /usr/local/bin/usb_tund")
sudossh("chmod 755 /usr/local/bin/usb_tund")

# Scripts
for sname in ["setup_gadget.sh", "setup_nat.sh"]:
    data = read_clean(os.path.join(LOCAL_BASE, "ubuntu", "scripts", sname)).rstrip(b"\n") + b"\n"
    chan_upload("/home/xlong/" + sname, data)
    sudossh("cp /home/xlong/" + sname + " /usr/local/bin/" + sname)
    sudossh("sed -i 's/\\r$//' /usr/local/bin/" + sname)
    sudossh("chmod 755 /usr/local/bin/" + sname)
    print("  {} deployed".format(sname))

# Web panel + echo
wp_data = read_clean(os.path.join(LOCAL_BASE, "ubuntu", "web_panel.py")).rstrip(b"\n") + b"\n"
chan_upload("/home/xlong/web_panel.py", wp_data)
sudossh("sed -i 's/\\r$//' /home/xlong/web_panel.py")

ec_data = read_clean(os.path.join(LOCAL_BASE, "tun_nat_hub_pkg", "web", "echo_srv.py"))
if not ec_data:
    # Generate inline
    ec_code = "import socket, threading\n\ndef handle(conn):\n    try:\n        data = conn.recv(4096)\n        if data:\n            conn.send(data)\n        conn.close()\n    except:\n        pass\n\ns = socket.socket(socket.AF_INET, socket.SOCK_STREAM)\ns.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)\ns.bind((\"10.0.0.1\", 9999))\ns.listen(5)\nprint(\"TCP_ECHO_READY\", flush=True)\nwhile True:\n    conn, addr = s.accept()\n    threading.Thread(target=handle, args=(conn,)).start()\n"
    ec_data = ec_code.encode()
else:
    ec_data = ec_data.replace(b"\r\n", b"\n").replace(b"\r", b"").rstrip(b"\n") + b"\n"
chan_upload("/home/xlong/echo_srv.py", ec_data)

# Systemd
svc = b"""[Unit]
Description=TUN NAT Hub USB Bridge (g_serial Pure Bulk)
After=network.target systemd-udev-settle.service
Wants=systemd-udev-settle.service
Requires=network.target
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
Type=simple
User=root
Group=root
ExecStartPre=-/usr/local/bin/setup_gadget.sh
ExecStartPre=/usr/local/bin/setup_nat.sh
ExecStart=/usr/local/bin/usb_tund
Restart=always
RestartSec=5
LimitNOFILE=65536
LimitNPROC=256
StandardOutput=journal
StandardError=journal
SyslogIdentifier=tun_nat_hub

[Install]
WantedBy=multi-user.target
"""

tun_web_svc = b"""[Unit]
Description=TUN NAT Hub Web Config Panel
After=network.target tun_nat_hub.service
Wants=tun_nat_hub.service

[Service]
Type=simple
User=root
ExecStart=/usr/bin/python3 /home/xlong/web_panel.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""

chan_upload("/home/xlong/tun_nat_hub_master.service", svc)
chan_upload("/home/xlong/tun_web_master.service", tun_web_svc)
sudossh("cp /home/xlong/tun_nat_hub_master.service /etc/systemd/system/tun_nat_hub.service")
sudossh("cp /home/xlong/tun_web_master.service /etc/systemd/system/tun_web.service")
sudossh("systemctl daemon-reload")

# ── Start ──
print()
print("=== Start ===")
sudossh("systemctl start tun_nat_hub 2>&1")
time.sleep(3)
sudossh("systemctl start tun_web 2>&1")
time.sleep(1)

# Echo
ssh("killall -9 python3 2>/dev/null; true")
time.sleep(0.5)
ssh("nohup python3 /home/xlong/echo_srv.py > /home/xlong/echo_out.txt 2>&1 &")
time.sleep(1)

# ── Verify ──
print()
print("=== Verify ===")
ssh("systemctl is-active tun_nat_hub tun_web 2>&1")
ssh("ls -la /dev/ttyGS0 2>&1")
ssh("ip -br addr show tun_hub 2>&1")
ssh("ss -tlnp 2>&1 | grep -E '8080|9999'")
ssh("curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8080/ 2>&1")
ssh("cat /home/xlong/echo_out.txt 2>&1")
ssh("/usr/local/bin/usb_tund 2>&1 | head -1; true")

print()
print("=== master branch deployed! ===")
print("Web panel: http://192.168.88.66:8080")
c.close()
