"""部署 CH5/CH6 对调版到 /tmp 手动运行测试"""
import paramiko, time, base64

V3S = "192.168.144.66"
LOCAL = r"c:\my_project\TUN_NAT_HUB\ubuntu\build_v3s\dji_rc"
REMOTE = "/tmp/dji_rc_ch56"
LOG = "/var/log/dji_rc_ch56.log"

data = open(LOCAL, "rb").read()
b64 = base64.b64encode(data).decode()
print("对调版大小:", len(data))

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

print("\n=== 2. 停旧 dji_rc ===")
print(r("killall dji_rc 2>/dev/null; sleep 2; echo ok"))

print("\n=== 3. 启动对调版 (SBUS 模式) ===")
print(r(REMOTE + " --interval 20 --out-dev /dev/ttyS0 --out-baud auto --crsf-telem 1 --rcmsg-host 10.0.0.2 --rcmsg-port 65530 > " + LOG + " 2>&1 & echo PID=$!"))

print("\n=== 4. 等 6 秒, 看 CH 行 ===")
time.sleep(6)
print(r("grep 'CH1=' " + LOG + " | tail -5"))
print("\n=== 5. 进程 ===")
print(r("ps w | grep dji_rc_ch56 | grep -v grep || echo 挂了!"))
c.close()
print("\n[done]")
