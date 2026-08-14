# -*- coding: utf-8 -*-
"""同步 V3s udp_send/udp_ping 到统一 magic 版 (更稳: 每块校验长度)"""
import paramiko, socket, time, base64, hashlib

def connect():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect("192.168.144.66", 22, "root", "root", timeout=20, allow_agent=False, look_for_keys=False)
    return c

def run(c, cmd, t=30):
    try:
        _, o, e = c.exec_command(cmd, timeout=t)
        return (o.read() + e.read()).decode(errors="replace").strip()
    except Exception as ex:
        return f"ERR: {ex}"

def upload(c, local, remote):
    b64 = base64.b64encode(open(local, "rb").read()).decode()
    want = hashlib.md5(open(local, "rb").read()).hexdigest()
    print(f"  上传 {remote}: b64={len(b64)} 目标md5={want}")
    run(c, f"rm -f {remote}.b64; echo cleared")
    CHUNK = 2000
    for i in range(0, len(b64), CHUNK):
        chunk = b64[i:i+CHUNK]
        # 用独立连接 + 校验返回
        cc = connect()
        r = run(cc, f"echo -n '{chunk}' >> {remote}.b64; echo OK", t=15)
        cc.close()
        if "OK" not in r:
            print(f"    chunk {i//CHUNK} 失败: {r}")
            return False
    # 校验 b64 长度
    cc = connect()
    gotlen = run(cc, f"wc -c {remote}.b64 | awk '{{print $1}}'")
    cc.close()
    print(f"  远端 b64 长度: {gotlen} (期望 {len(b64)})")
    if gotlen.strip() != str(len(b64)):
        print("  长度不符, 重新上传...")
        return upload(c, local, remote)
    cc = connect()
    got = run(cc, f"base64 -d {remote}.b64 > {remote} && chmod +x {remote} && md5sum {remote} | awk '{{print $1}}'")
    cc.close()
    ok = got == want
    print(f"  {remote}: {'OK' if ok else 'MD5 MISMATCH ' + got}")
    return ok

c = connect()
print("=== 同步 udp_send + udp_ping ===")
ok1 = upload(c, r"c:\my_project\TUN_NAT_HUB\tmp\udp_send", "/tmp/udp_send")
ok2 = upload(c, r"c:\my_project\TUN_NAT_HUB\tmp\udp_ping", "/tmp/udp_ping")
c.close()
print(f"\nudp_send: {'OK' if ok1 else 'FAIL'} | udp_ping: {'OK' if ok2 else 'FAIL'}")
