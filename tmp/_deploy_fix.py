"""部署 UDP 非阻塞修复版到 /tmp, 验证主循环不再卡死"""
import paramiko, time, base64

V3S = "192.168.144.66"
LOCAL = r"c:\my_project\TUN_NAT_HUB\ubuntu\build_v3s\dji_rc"
REMOTE = "/tmp/dji_rc_fix"
LOG = "/var/log/dji_rc_fix.log"

data = open(LOCAL, "rb").read()
b64 = base64.b64encode(data).decode()
print("修复版大小:", len(data))

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(V3S, 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=2.0, stdin_data=None):
    stdin, out, err = c.exec_command(cmd)
    if stdin_data is not None:
        stdin.write(stdin_data)
        stdin.channel.shutdown_write()
    time.sleep(wait)
    return (out.read() + err.read()).decode(errors="replace").strip()

print("\n=== 1. 传输 ===")
print(r("base64 -d > " + REMOTE, wait=3.0, stdin_data=b64))
print("md5:", r("chmod +x " + REMOTE + "; md5sum " + REMOTE))

print("\n=== 2. 停旧诊断版 ===")
print(r("killall dji_rc_diag dji_rc 2>/dev/null; killall getty 2>/dev/null; sleep 2; echo ok"))

print("\n=== 3. 启动修复版 ===")
print(r(REMOTE + " --interval 20 --out-dev /dev/ttyS0 --out-baud auto --crsf-telem 1 --rcmsg-host 10.0.0.2 --rcmsg-port 65530 > " + LOG + " 2>&1 & echo 启动PID=$!"))

print("\n=== 4. 等 15 秒, 验证主循环+PB6 poll 持续运行 ===")
time.sleep(15)
print("CH 行数:", r("grep -c 'CH1=' " + LOG))
print("PB6 行数:", r("grep -c 'PB6 DATA' " + LOG))
print("rcmsg fail:", r("grep -c 'rcmsg send fail' " + LOG + " || echo 0"))
print("\n=== 5. 进程 + 主线程 wchan (应不在 sock_alloc_send_pskb) ===")
pid = r("pgrep -f dji_rc_fix | head -1")
print("PID:", pid)
print(r("cat /proc/" + pid + "/task/" + pid + "/wchan 2>/dev/null || echo 无"))
print("\n=== 6. 日志尾 6 行 ===")
print(r("tail -6 " + LOG))
c.close()
print("\n[done]")
