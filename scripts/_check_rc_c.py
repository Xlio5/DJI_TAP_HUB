"""检查 V3s 上 dji_rc 的 C1/C2/C3 解码值, 对比按键区与 SBUS"""
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

def r(cmd, wait=0.5):
    _, out, err = c.exec_command(cmd)
    time.sleep(wait)
    return (out.read() + err.read()).decode(errors="replace").strip()

print("=== dji_rc 当前状态文件 ===")
print(r("cat /var/log/rc_state.json 2>/dev/null | head -1 || echo no-state"))

print("\n=== dji_rc 控制台最近输出 (C1/C2/C3 和 SBUS) ===")
print(r("tail -5 /var/log/dji_rc.log 2>/dev/null || ls -la /var/log/dji_rc.log"))

print("\n=== 连续 3 次采样状态文件, 看 C1/C2/C3/DIAL 变化 ===")
for i in range(3):
    out = r("cat /var/log/rc_state.json 2>/dev/null")
    # 提取关键字段
    import re
    if out:
        c1 = re.search(r'"c1":(\d+)', out)
        c2 = re.search(r'"c2":(\d+)', out)
        c3 = re.search(r'"c3":(\d+)', out)
        d = re.search(r'"dial":(\d+)', out)
        ch14 = re.search(r'"ch14":(\d+)', out)
        ch15 = re.search(r'"ch15":(\d+)', out)
        print(f"  采样{i+1}: c1={c1.group(1) if c1 else '?'} c2={c2.group(1) if c2 else '?'} "
              f"c3={c3.group(1) if c3 else '?'} dial={d.group(1) if d else '?'} "
              f"CH14={ch14.group(1) if ch14 else '?'} CH15={ch15.group(1) if ch15 else '?'}")
    time.sleep(1)

c.close()
print("\n[done]")
