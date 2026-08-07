"""部署正式版 dji_rc (先杀进程再传输, 避免 Text file busy)"""
import paramiko, time, base64

V3S = "192.168.144.66"
LOCAL = r"c:\my_project\TUN_NAT_HUB\ubuntu\build_v3s\dji_rc"
REMOTE = "/tmp/dji_rc"
LOG = "/var/log/dji_rc_poll.log"
EXPECT = "54e2a7236932a0518c1548b09ffa7b4a"

data = open(LOCAL, "rb").read()
b64 = base64.b64encode(data).decode()
print("正式版大小:", len(data), "B, 期望 md5:", EXPECT)

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

print("\n=== 1. 先杀进程 + 删文件 ===")
print(r("killall dji_rc 2>/dev/null; killall getty 2>/dev/null; sleep 2; rm -f " + REMOTE + " " + LOG + "; ls -la " + REMOTE + " 2>&1"))

print("\n=== 2. 再传输正式版 ===")
print(r("base64 -d > " + REMOTE, wait=3.0, stdin_data=b64))
md5 = r("chmod +x " + REMOTE + "; md5sum " + REMOTE)
print(md5)
print("MATCH ✓" if EXPECT in md5 else "MD5 MISMATCH ✗")

print("\n=== 3. 启动 ===")
print(r("/tmp/dji_rc --interval 20 --out-dev /dev/ttyS0 --out-baud auto --crsf-telem 1 --rcmsg-host 10.0.0.2 --rcmsg-port 65530 > " + LOG + " 2>&1 & echo 启动PID=$!"))

print("\n=== 4. 等 8 秒, 启动日志 (正式版无刷屏, 仅首行诊断) ===")
time.sleep(8)
print(r("grep -E 'PB6|输出|模式|error|FAIL' " + LOG + " | head -8"))
print("\n=== 5. 进程存活 ===")
print(r("ps w | grep /tmp/dji_rc | grep -v grep || echo 进程挂了!"))
c.close()
print("\n[done]")
