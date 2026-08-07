"""M4 验证: 部署 bridge 固件 + 启动 bridge 模式 + 验证 UDP 转发
前提: 设备 SSH 可达 + ELRS 模块接 UART0
"""
import paramiko, time, socket, base64

HOST = "192.168.144.66"
FW = r"c:\my_project\TUN_NAT_HUB\backup\rootfs_bridge.squashfs"
data = open(FW, "rb").read()

def ssh_cmd(cmd, wait=1.5):
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    out = (o.read() + e.read()).decode(errors="replace").strip()
    c.close()
    return out

def wait_online(timeout=120):
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            s = socket.create_connection((HOST, 22), timeout=3)
            s.close()
            return True
        except Exception:
            time.sleep(3)
    return False

print("=== 1. 探测设备 ===")
if not wait_online(30):
    print("设备离线! 请先给 V3s 上电联网")
    raise SystemExit(1)
print("设备在线")

print("\n=== 2. 当前状态 ===")
print("槽位:", ssh_cmd("cat /proc/cmdline | grep -o 'root=/dev/mtdblock[0-9]'"))
print("dji_rc:", ssh_cmd("md5sum /usr/local/bin/dji_rc"))

print("\n=== 3. OTA 上传 bridge 固件 ===")
import http.client
conn = http.client.HTTPConnection(HOST, 8080, timeout=300)
conn.request("POST", "/api/firmware/upload", body=data, headers={
    "Content-Type": "application/octet-stream", "Content-Length": str(len(data))})
resp = conn.getresponse()
body = resp.read().decode(errors="replace")
conn.close()
print("上传:", resp.status, body)

if '"ok":true' in body:
    try: ssh_cmd("sync; reboot", wait=1)
    except Exception: pass
    print("重启中...")
    if wait_online(150):
        time.sleep(12)
        print("\n设备上线")
        print("新槽:", ssh_cmd("cat /proc/cmdline | grep -o 'root=/dev/mtdblock[0-9]'"))
        print("dji_rc:", ssh_cmd("md5sum /usr/local/bin/dji_rc"))
    else:
        print("设备未上线!")
else:
    print("OTA 失败")
