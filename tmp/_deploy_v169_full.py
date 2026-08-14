#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""部署 v169 dji_rc 到 V3s /tmp + 替换运行 + 测 UDP->bridge 转发"""
import base64
import hashlib
import paramiko
import socket
import time

HOST = "192.168.144.66"
LOCAL = r"ubuntu\build_v3s\dji_rc"  # v169 编译产物

def main():
    data = open(LOCAL, "rb").read()
    b64 = base64.b64encode(data).decode()
    want = hashlib.md5(data).hexdigest()

    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    sock = socket.create_connection((HOST, 22), timeout=5)
    c.connect(HOST, username="root", password="root", timeout=5, sock=sock)

    def run(cmd, t=10, tries=3):
        for _ in range(tries):
            try:
                _, out, _ = c.exec_command(cmd, timeout=t)
                return out.read().decode(errors="replace")
            except Exception:
                time.sleep(0.5)
        return "FAIL"

    print("== 传输 v169 dji_rc ==")
    run("rm -f /tmp/dji_rc.b64 /tmp/dji_rc_v169")
    for i in range(0, len(b64), 4096):
        run(f"echo -n '{b64[i:i+4096]}' >> /tmp/dji_rc.b64")
    r = run("base64 -d /tmp/dji_rc.b64 > /tmp/dji_rc_v169 && chmod +x /tmp/dji_rc_v169 && md5sum /tmp/dji_rc_v169")
    print("远程:", r.strip())
    print("本地:", want)
    if want not in r:
        print("!! md5 不匹配"); return

    print("== 替换运行 ==")
    print(run("killall dji_rc 2>&1; sleep 1; ps -ef | grep dji_rc | grep -v grep || echo 已停"))
    cmd = ("nohup /tmp/dji_rc_v169 --interval 20 --out-dev /dev/ttyS0 --out-baud 400000 "
           "--crsf-telem 1 --rcmsg-host 10.0.0.2 --rcmsg-port 65530 --crsf-bridge "
           "--crsfbr-host 10.0.0.2 --crsfbr-port 65532 > /var/log/dji_rc.log 2>&1 &")
    run(cmd)
    time.sleep(3)
    print(run("ps -ef | grep dji_rc_v169 | grep -v grep || echo 进程没了"))
    print("== 启动日志 ==")
    print(run("grep -a 'bridge 线程\\|监听 UDP\\|baud' /var/log/dji_rc.log | head -5"))

    print("== 测 UDP -> bridge ==")
    print(run("/tmp/udp_send 10.0.0.1 65532"))
    time.sleep(0.5)
    print("== bridge recv 日志 ==")
    print(run("grep -a 'bridge recv\\|bridge fwd' /var/log/dji_rc.log | tail -5") or "(无)")
    c.close()

if __name__ == "__main__":
    main()
