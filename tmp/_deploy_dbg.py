#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""部署调试版 dji_rc 到 V3s /tmp + 启动 (stdin 传输, 严格 md5)"""
import base64
import hashlib
import paramiko
import socket
import time

HOST = "192.168.144.66"
LOCAL = r"tmp\dji_rc_dbg_arm"

def main():
    data = open(LOCAL, "rb").read()
    b64 = base64.b64encode(data).decode()
    want = hashlib.md5(data).hexdigest()
    print("本地 md5:", want)

    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    for _ in range(5):
        try:
            sock = socket.create_connection((HOST, 22), timeout=5)
            c.connect(HOST, username="root", password="root", timeout=5, sock=sock)
            break
        except Exception as e:
            print("连接重试:", e); time.sleep(2)
    else:
        print("无法连接"); return

    def run(cmd, t=10, tries=4):
        for _ in range(tries):
            try:
                _, out, _ = c.exec_command(cmd, timeout=t)
                return out.read().decode(errors="replace")
            except Exception:
                time.sleep(1)
        return "ERR"

    run("killall dji_rc_v169 dji_rc 2>/dev/null; rm -f /tmp/dji_rc.b64")
    stdin, stdout, _ = c.exec_command("cat > /tmp/dji_rc.b64", timeout=30)
    stdin.write(b64); stdin.flush(); stdin.channel.shutdown_write(); stdout.read()
    r = run("base64 -d /tmp/dji_rc.b64 > /tmp/dji_rc_v169 && chmod +x /tmp/dji_rc_v169 && md5sum /tmp/dji_rc_v169")
    print("部署 md5:", r.strip())
    if want not in r:
        print("!! md5 不匹配, 中止"); c.close(); return

    run("setsid /tmp/dji_rc_v169 --interval 20 --out-dev /dev/ttyS0 --out-baud 115200 "
        "--crsf-telem 1 --rcmsg-host 10.0.0.2 --rcmsg-port 65530 --crsf-bridge "
        "--crsfbr-host 10.0.0.2 --crsfbr-port 65532 < /dev/null > /var/log/dji_rc.log 2>&1 &")
    time.sleep(4)
    print("进程数:", run("ps -ef | grep dji_rc_v169 | grep -v grep | wc -l").strip())
    c.close()

if __name__ == "__main__":
    main()
