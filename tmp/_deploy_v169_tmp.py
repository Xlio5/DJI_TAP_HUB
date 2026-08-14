#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""重启 V3s 现有 dji_rc, 显式 --out-baud 400000 (旧二进制支持该参数, 400000≠0 不触发 420000 兜底)
   不刷 rootfs, 不传文件。重启后失效(S99 仍 auto)。用于 ELRS 链路调试。"""
import paramiko
import time

HOST = "192.168.144.66"
USER = "root"
PASS = "root"

def main():
    import socket
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    connected = False
    for attempt in range(3):
        try:
            sock = socket.create_connection((HOST, 22), timeout=5)
            c.connect(HOST, port=22, username=USER, password=PASS,
                      timeout=5, sock=sock)
            connected = True
            break
        except Exception as e:
            print(f"连接尝试 {attempt + 1} 失败: {type(e).__name__}: {e}")
            time.sleep(1)
    if not connected:
        print("无法连接 V3s"); return
    print(f"LOGIN OK {HOST}")

    def run(cmd):
        _, out, err = c.exec_command(cmd, timeout=10)
        return out.read().decode(errors="replace"), err.read().decode(errors="replace")

    print("== 杀旧 dji_rc ==")
    o, _ = run("killall dji_rc 2>&1; sleep 1; ps -ef | grep dji_rc | grep -v grep || echo '已停'")
    print(o.strip())

    print("== 用现有 dji_rc @400000 重启 ==")
    cmd = ("nohup /usr/local/bin/dji_rc --interval 20 --out-dev /dev/ttyS0 --out-baud 400000 "
           "--crsf-telem 1 --rcmsg-host 10.0.0.2 --rcmsg-port 65530 --crsf-bridge "
           "--crsfbr-host 10.0.0.2 --crsfbr-port 65532 > /var/log/dji_rc.log 2>&1 &")
    o, _ = run(cmd)
    time.sleep(3)

    print("== 进程检查 ==")
    o, _ = run("ps -ef | grep dji_rc | grep -v grep")
    print(o.strip() or "!! 进程不存在, 看日志")

    print("== dji_rc 日志 (波特率确认) ==")
    o, _ = run("grep -E 'crsf-bridge|baud|bridge|启动' /var/log/dji_rc.log | head -10")
    print(o[:1200] or "(无匹配, 看完整头30行)")
    o, _ = run("head -30 /var/log/dji_rc.log")
    print(o[:800])

if __name__ == "__main__":
    main()
