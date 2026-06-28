"""Probe V3s system info via SSH."""
import paramiko, sys

HOST = "192.168.88.66"
DIAG_CMD = (
    "uname -a && echo '--MODEL--' && "
    "cat /proc/device-tree/model 2>/dev/null || echo no-dtb-model && echo '--MEM--' && "
    "free && echo '--UDC--' && ls /sys/class/udc/ 2>/dev/null || echo no-udc && echo '--DISK--' && "
    "df -h / 2>/dev/null && echo '--IFACES--' && "
    "ip -br addr 2>/dev/null || ifconfig && echo '--KERNEL--' && "
    "cat /proc/version 2>/dev/null; uname -r && echo '--MODULES--' && "
    "lsmod 2>/dev/null | head -15 && echo '--IPTABLES--' && "
    "iptables -L -n 2>/dev/null | head -5; iptables -t nat -L -n 2>/dev/null | head -5 && echo '--INIT--' && "
    "cat /etc/inittab 2>/dev/null | head -5 || echo no-inittab ; "
    "ls /etc/init.d/ 2>/dev/null | head -20 || echo no-init-d"
)

def probe(host=HOST):
    """Try common V3s/Buildroot credentials, return diagnostic output."""
    for user, pw in [("root", ""), ("root", "root"), ("root", "1234"), ("root", "licheepi")]:
        try:
            c = paramiko.SSHClient()
            c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            c.connect(host, username=user, password=pw, timeout=5)
            stdin, stdout, stderr = c.exec_command(DIAG_CMD, timeout=15, get_pty=True)
            # Wait for command completion, then read all output
            exit_status = stdout.channel.recv_exit_status()
            out = stdout.read().decode(errors="replace")
            err = stderr.read().decode(errors="replace")
            print(f"LOGIN: {user}:{pw} OK")
            if out:
                print(out)
            if err:
                print("--- STDERR ---")
                print(err)
            c.close()
            return exit_status
        except Exception as e:
            print(f"LOGIN: {user}:{pw} FAIL ({e})")
    return 1


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else HOST
    sys.exit(probe(target))
