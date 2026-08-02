"""抓取 SPECIAL/0x02 的原始 payload, 分析按键字节 (pl[10..12]) 里有没有 C1/C2/C3 位"""
import paramiko, time

def ssh_connect(host, user, pw, retries=5, timeout=12):
    for i in range(retries):
        try:
            c = paramiko.SSHClient()
            c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            c.connect(host, 22, user, pw, timeout=timeout, allow_agent=False,
                      look_for_keys=False, banner_timeout=timeout, auth_timeout=timeout)
            return c
        except Exception as e:
            print(f"  [重试{i+1}] {e}")
            time.sleep(2)
    return None

c = ssh_connect("192.168.144.66", "root", "root")
if not c:
    print("V3s SSH 失败")
    exit(1)

def r(cmd, wait=0.6):
    _, out, err = c.exec_command(cmd)
    time.sleep(wait)
    return (out.read() + err.read()).decode(errors="replace").strip()

print("=== 当前 dji_rc 是否带调试输出 (dbg_b payload) ===")
print(r("ps w | grep dji_rc | grep -v grep"))

print("\n=== 抓 SPECIAL/0x02 payload: 用 dji_rc 的 dbg_b (最近一帧的前16字节) ===")
# rc_state.json 里没有 payload, 需要从 dji_rc 调试输出或抓串口
# 检查是否有 uart_echo / 抓包工具
print(r("ls /usr/local/bin/ 2>/dev/null | grep -iE 'dji|echo|dump|sniff'"))

print("\n=== 从 dmesg 或 dji_rc 日志找 payload 线索 ===")
print(r("tail -20 /var/log/dji_rc.log 2>/dev/null | head -20"))

print("\n=== 尝试直接读串口抓 SPECIAL 包 (ttyS1) ===")
# 抓几秒 ttyS1 的原始字节
print(r("dd if=/dev/ttyS1 bs=1 count=200 2>/dev/null | xxd | head -30 & DP=$!; sleep 2; kill $DP 2>/dev/null"))

c.close()
print("\n[done]")
