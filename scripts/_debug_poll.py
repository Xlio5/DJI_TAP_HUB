"""观察 dji_rc pb6-poll 调试日志 (定位运行中切换)"""
import paramiko, time

PC, V3S = "192.168.144.88", "192.168.144.66"

def ssh_r(cmd, wait=2.0):
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(V3S, 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)
    _, out, err = c.exec_command(cmd)
    time.sleep(wait)
    r = (out.read() + err.read()).decode(errors="replace").strip()
    c.close()
    return r

print("=== 1. 下载调试版 + 启动 ===")
print(ssh_r(f"wget -q -O /tmp/dji_dbg http://{PC}:9899/dji_rc 2>&1; chmod +x /tmp/dji_dbg; md5sum /tmp/dji_dbg"))
print(ssh_r("killall dji_rc dji_p dji_dbg 2>/dev/null; sleep 1; (/tmp/dji_dbg --interval 20 --out-dev /dev/ttyS0 --out-baud auto --crsf-telem 1 --rcmsg-host 10.0.0.2 --rcmsg-port 65530 > /var/log/dji_rc.log 2>&1 &); sleep 5; echo '--- pb6-poll 前 8 条 ---'; grep 'pb6-poll' /var/log/dji_rc.log | head -8"))
c.close()
print("\n[done]")
