#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分块 base64 传输 udp_send 到 V3s /tmp 并运行 (发 ping 到 10.0.0.1:65532)"""
import base64
import hashlib
import paramiko
import socket

HOST = "192.168.144.66"
LOCAL = r"tmp\udp_send_arm"

def main():
    b64 = base64.b64encode(open(LOCAL, "rb").read()).decode()
    local_md5 = hashlib.md5(open(LOCAL, "rb").read()).hexdigest()

    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    sock = socket.create_connection((HOST, 22), timeout=5)
    c.connect(HOST, username="root", password="root", timeout=5, sock=sock)

    def run(cmd):
        _, out, _ = c.exec_command(cmd, timeout=15)
        return out.read().decode(errors="replace")

    run("rm -f /tmp/udp_send.b64")
    CHUNK = 500
    for i in range(0, len(b64), CHUNK):
        seg = b64[i:i + CHUNK]
        run(f"echo '{seg}' >> /tmp/udp_send.b64")
    print(f"base64 分块 {len(b64)}/{CHUNK} 段完成")

    print(run("base64 -d /tmp/udp_send.b64 > /tmp/udp_send && chmod +x /tmp/udp_send"))
    print("远程:", run("md5sum /tmp/udp_send"))
    print("本地:", local_md5)

    print("== 运行 udp_send (发 5x Device_Ping -> 10.0.0.1:65532) ==")
    print(run("/tmp/udp_send 10.0.0.1 65532"))
    c.close()

if __name__ == "__main__":
    main()
