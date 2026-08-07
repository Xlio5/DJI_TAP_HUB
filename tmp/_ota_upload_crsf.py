"""OTA 上传 rootfs_crsf (CRSF 增强版) 到设备 + 确认切槽"""
import http.client, paramiko, time, socket

HOST = "192.168.144.66"
FW = r"c:\my_project\TUN_NAT_HUB\backup\rootfs_crsf.squashfs"
data = open(FW, "rb").read()
print(f"固件: {len(data)} bytes, magic {data[:4]}")

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

print("当前槽:", ssh_cmd("cat /proc/cmdline | grep -o 'root=/dev/mtdblock[0-9]'"))

# 上传
conn = http.client.HTTPConnection(HOST, 8080, timeout=300)
conn.request("POST", "/api/firmware/upload", body=data, headers={
    "Content-Type": "application/octet-stream",
    "Content-Length": str(len(data)),
})
resp = conn.getresponse()
body = resp.read().decode(errors="replace")
conn.close()
print("上传:", resp.status, body)

if '"ok":true' in body:
    # 重启
    try:
        ssh_cmd("sync; reboot", wait=1)
        print("重启命令已发送")
    except Exception as e:
        print("重启异常:", e)
    if wait_online(120):
        time.sleep(10)
        print("设备上线, 新槽:", ssh_cmd("cat /proc/cmdline | grep -o 'root=/dev/mtdblock[0-9]'"))
        print("dji_rc md5 (应 9f867cf9):", ssh_cmd("md5sum /usr/local/bin/dji_rc"))
    else:
        print("设备未上线!")
