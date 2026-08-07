"""分析解码健康度: g1/g2 增长 + CH5/CH6 历史 + 解码异常"""
import paramiko, time, re

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("=== 1. 历史 CH5/CH6 非零记录 (整个日志) ===")
print(r("grep 'CH1=' /var/log/dji_rc.log 2>/dev/null | grep -vE 'CH5=\\+0 CH6=\\+0' | tail -10"))
print("(空 = 全程 CH5/CH6 都是 0)")
print("\n=== 2. g1/g2 近 10 条 (解码计数) ===")
print(r("grep 'CH1=' /var/log/dji_rc.log 2>/dev/null | tail -10 | grep -oE 'g1=[0-9]+ g2=[0-9]+'"))
print("\n=== 3. 日志里 decode/解析相关行 ===")
print(r("grep -iE 'decode|selftest|RC/0xAE|SPECIAL' /var/log/dji_rc.log 2>/dev/null | head -10"))
print("\n=== 4. 日志总行数 + 启动时间 ===")
print(r("wc -l /var/log/dji_rc.log 2>/dev/null; head -1 /var/log/dji_rc.log"))
c.close()
print("\n[done]")
