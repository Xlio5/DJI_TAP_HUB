"""OTA 连续 20 次循环测试 (无缓冲实时输出)
每次: 探测在线 → OTA上传 → 重启 → 确认切槽
用法: python -u _ota_loop20.py [起始次数]
"""
import http.client, paramiko, time, sys, socket, os

HOST = "192.168.144.66"
FW = r"c:\my_project\TUN_NAT_HUB\backup\rootfs_v150.squashfs"
START = int(sys.argv[1]) if len(sys.argv) > 1 else 1

data = open(FW, "rb").read()
print(f"OTA 固件: {len(data)} bytes", flush=True)

def ssh_cmd(cmd, wait=2.0):
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

def ota_upload():
    conn = http.client.HTTPConnection(HOST, 8080, timeout=120)
    conn.request("POST", "/api/firmware/upload", body=data, headers={
        "Content-Type": "application/octet-stream",
        "Content-Length": str(len(data)),
    })
    resp = conn.getresponse()
    body = resp.read().decode(errors="replace")
    conn.close()
    return resp.status, body

def get_slot():
    try:
        return ssh_cmd("cat /proc/cmdline | grep -o 'root=/dev/mtdblock[0-9]'")
    except Exception:
        return "?"

print("=== OTA 循环开始 (从第 %d 次, 共20次) ===" % START, flush=True)
results = []
ok_cnt = 0
for i in range(START, START + 20):
    t0 = time.time()
    # 0. 确保设备在线
    if not wait_online(60):
        print(f"[{i}] 设备离线, 跳过 (60s 超时)", flush=True)
        results.append((i, "?", "?", False, False, 0))
        continue
    # 1. 当前槽
    cur = get_slot()
    # 2. OTA 上传
    try:
        status, resp = ota_upload()
        ok = status == 200 and '"ok":true' in resp
        resp_short = resp[:60]
    except Exception as e:
        status, ok, resp_short = -1, False, str(e)[:60]
    # 3. 重启
    if ok:
        try:
            ssh_cmd("sync; reboot", wait=1)
        except Exception:
            pass
        time.sleep(3)
        up = wait_online(120)
    else:
        up = False
    # 4. 确认新槽
    if up:
        time.sleep(8)
        new = get_slot()
        if new == cur:  # 可能没切, 再等几秒
            time.sleep(10)
            new = get_slot()
    else:
        new = "?"
    dt = time.time() - t0
    switched = (new != cur and new != "?")
    result = "✓" if (ok and up and switched) else "✗"
    if ok and up and switched:
        ok_cnt += 1
    print(f"[{i}] {dt:.0f}s cur={cur} → new={new} 上传={'OK' if ok else 'FAIL'} 重启={'UP' if up else 'DOWN'} {result} {resp_short}", flush=True)
    results.append((i, cur, new, ok, up, dt))
    time.sleep(2)

print(f"\n=== 汇总: 成功 {ok_cnt}/20 ===", flush=True)
print("失败详情:", flush=True)
for i, cur, new, ok, up, dt in results:
    if not (ok and up and new != cur and new != "?"):
        print(f"  第{i}次: cur={cur} new={new} 上传={ok} 重启={up}", flush=True)
print("DONE", flush=True)
