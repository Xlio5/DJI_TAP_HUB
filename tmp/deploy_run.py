"""部署新 mmap 版 dji_rc 到 /tmp (base64 经 stdin) 并手动启动, 观察 PB6 poll"""
import paramiko, time, base64

V3S = "192.168.144.66"
LOCAL = r"c:\my_project\TUN_NAT_HUB\ubuntu\build_v3s\dji_rc"
REMOTE = "/tmp/dji_rc"
LOG = "/var/log/dji_rc_poll.log"

# 读本地二进制, base64 编码 (SFTP 在 V3s 上不可用, 改用 base64 经 exec stdin)
data = open(LOCAL, "rb").read()
b64 = base64.b64encode(data).decode()
print("本地 dji_rc 大小:", len(data), "B, base64:", len(b64), "B")

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(V3S, 22, "root", "root", timeout=10, allow_agent=False, look_for_keys=False)

def r(cmd, wait=2.0, stdin_data=None):
    stdin, out, err = c.exec_command(cmd)
    if stdin_data is not None:
        stdin.write(stdin_data)
        stdin.channel.shutdown_write()
    time.sleep(wait)
    return (out.read() + err.read()).decode(errors="replace").strip()

print("\n=== 1. 传输 (base64 -> base64 -d) ===")
print(r("base64 -d > " + REMOTE, wait=3.0, stdin_data=b64))
print("md5+chmod:", r("chmod +x " + REMOTE + "; md5sum " + REMOTE))

print("\n=== 2. 清场 (杀旧 dji_rc/getty + 旧日志) ===")
print(r("killall dji_rc 2>/dev/null; killall getty 2>/dev/null; sleep 1; echo ok"))

print("\n=== 3. 启动新 dji_rc (/tmp) ===")
print(r("/tmp/dji_rc --interval 20 --out-dev /dev/ttyS0 --out-baud auto --crsf-telem 1 --rcmsg-host 10.0.0.2 --rcmsg-port 65530 > " + LOG + " 2>&1 & echo 启动PID=$!"))

print("\n=== 4. 等 5 秒, 启动日志 ===")
time.sleep(5)
print(r("cat " + LOG))
c.close()
print("\n[done]")
