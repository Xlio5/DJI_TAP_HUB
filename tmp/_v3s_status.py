#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SSH 查 V3s 当前跑的程序 + UART0 波特率"""
import paramiko
import sys

HOST = "192.168.144.66"
CMDS = [
    ("进程", "ps -ef | grep -E 'dji_rc|uart_bridge|udp_send|udp_ping|usb_tund' | grep -v grep"),
    ("/tmp 测试工具", "ls -la /tmp/ 2>/dev/null | grep -E 'bridge|udp|ping' | head -10"),
    ("dji_rc 日志", "cat /var/log/dji_rc.log 2>/dev/null | tail -25"),
    ("UART0 波特率", "stty -F /dev/ttyS0 2>&1 | head -3"),
]

def main():
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    logged = False
    for user, pw in [("root", ""), ("root", "root"), ("root", "1234"), ("root", "licheepi")]:
        try:
            c.connect(HOST, username=user, password=pw, timeout=5)
            print(f"LOGIN OK: {user}:{pw}")
            logged = True
            break
        except Exception as e:
            print(f"LOGIN FAIL {user}:{pw}: {e}")
    if not logged:
        print("无法登录 V3s"); return
    for name, cmd in CMDS:
        print(f"\n===== {name} =====")
        _, out, err = c.exec_command(cmd, timeout=10, get_pty=True)
        try:
            o = out.read().decode(errors="replace")
            e = err.read().decode(errors="replace")
        except Exception as ex:
            o = str(out.read().decode(errors="replace"))
            e = ""
        print(o or e or "(空)")

if __name__ == "__main__":
    main()
