"""OTA 上传 rootfs_ch56 (CRSF增强+CH5/CH6对调) 到设备"""
import http.client, paramiko, time, socket

HOST = "192.168.144.66"
FW = r"c:\my_project\TUN_NAT_HUB\backup\rootfs_ch56.squashfs"
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

# 确认当前状态
print("当前槽:", ssh_cmd("cat /proc/cmdline | grep -o 'root=/dev/mtdblock[0-9]'"))
print("当前 ctl:", ssh_cmd("dd if=/dev/mtdblock0 bs=1 skip=1032192 count=6 2>/dev/null | hexdump -C | head -1"))
print("当前运行 dji_rc:", ssh_cmd("ps w | grep -E 'dji_rc' | grep -v grep | head -2 | awk '{print $1, $NF}'"))

# 停掉 /tmp 测试版 (避免影响)
print("\n停 /tmp 测试版:", ssh_cmd("killall dji_rc_ch56 2>/dev/null; echo ok"))

# 上传
print("\n=== 上传 rootfs_ch56 ===")
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
    print("上传后 ctl:", ssh_cmd("dd if=/dev/mtdblock0 bs=1 skip=1032192 count=6 2>/dev/null | hexdump -C | head -1"))
    try:
        ssh_cmd("sync; reboot", wait=1)
        print("重启命令已发送")
    except Exception as e:
        print("重启异常:", e)
    if wait_online(150):
        time.sleep(12)
        print("\n设备上线")
        print("新槽:", ssh_cmd("cat /proc/cmdline | grep -o 'root=/dev/mtdblock[0-9]'"))
        print("dji_rc md5 (应 86f48284):", ssh_cmd("md5sum /usr/local/bin/dji_rc"))
    else:
        print("设备未上线!")
