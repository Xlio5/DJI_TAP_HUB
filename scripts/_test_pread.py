"""测试 pread/pwrite 版 dji_rc: 运行中切换"""
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

print("=== 1. 下载 + 启动 (当前接地) ===")
print(ssh_r(f"wget -q -O /tmp/dji_p http://{PC}:9899/dji_rc 2>&1; chmod +x /tmp/dji_p; md5sum /tmp/dji_p"))
print(ssh_r("killall dji_rc dji_p 2>/dev/null; sleep 1; (/tmp/dji_p --interval 20 --out-dev /dev/ttyS0 --out-baud auto --crsf-telem 1 --rcmsg-host 10.0.0.2 --rcmsg-port 65530 > /var/log/dji_rc.log 2>&1 &); sleep 4; grep -E 'PB6 检测|接地|debug 模式|输出 /dev' /var/log/dji_rc.log | head -6"))

print("\n=== 2. 当前 PB6 (接地=0) + 是否 debug ===")
print("DATA:", ssh_r("devmem 0x01C20834 2>/dev/null"))
print("getty:", ssh_r("ps w | grep getty | grep -v grep || echo '无 getty'"))
print("out:", ssh_r("grep -cE 'out ok' /var/log/dji_rc.log 2>/dev/null || echo 0"))
c.close()
print("\n[done]")
