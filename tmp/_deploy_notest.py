"""部署无对调版 (CRSF增强, 无CH5/CH6对调) 测 UART2"""
import paramiko, time, base64

V3S = "192.168.144.66"
LOCAL = r"c:\my_project\TUN_NAT_HUB\ubuntu\build_v3s\dji_rc"
REMOTE = "/tmp/dji_rc_notest"
LOG = "/var/log/dji_rc_notest.log"

data = open(LOCAL, "rb").read()
b64 = base64.b64encode(data).decode()

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

print("停 v150:", r("killall dji_rc_v150 2>/dev/null; sleep 1; echo ok"))
print("\n传输:", r("base64 -d > " + REMOTE, wait=3.0, stdin_data=b64))
print("md5:", r("chmod +x " + REMOTE + "; md5sum " + REMOTE))
print("\n启动:", r(REMOTE + " --interval 20 --out-dev /dev/ttyS0 --out-baud auto --crsf-telem 1 --rcmsg-host 10.0.0.2 --rcmsg-port 65530 > " + LOG + " 2>&1 & echo PID=$!"))
time.sleep(10)
print("\nrx1/rx2:", r("grep 'CH1=' " + LOG + " | tail -1 | grep -oE 'rx1=[0-9]* rx2=[0-9]*'"))
print("g1/g2:", r("grep 'CH1=' " + LOG + " | tail -1 | grep -oE 'g1=[0-9]* g2=[0-9]*'"))
c.close()
print("\n[done]")
