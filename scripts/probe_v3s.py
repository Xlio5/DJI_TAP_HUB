"""Probe V3s system info via SSH."""
import paramiko, time

HOST = "192.168.88.66"
# Try common V3s/Buildroot credentials
for user, pw in [("root", ""), ("root", "root"), ("root", "1234"), ("root", "licheepi")]:
    try:
        c = paramiko.SSHClient()
        c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        c.connect(HOST, username=user, password=pw, timeout=5)
        stdin, stdout, stderr = c.exec_command(
            "uname -a && echo '--MODEL--' && "
            "cat /proc/device-tree/model 2>/dev/null || echo no-dtb-model && echo '--MEM--' && "
            "free && echo '--UDC--' && ls /sys/class/udc/ 2>/dev/null || echo no-udc && echo '--DISK--' && "
            "df -h / 2>/dev/null && echo '--IFACES--' && "
            "ip -br addr 2>/dev/null || ifconfig && echo '--KERNEL--' && "
            "cat /proc/version 2>/dev/null; uname -r && echo '--MODULES--' && "
            "lsmod 2>/dev/null | head -15 && echo '--IPTABLES--' && "
            "iptables -L -n 2>/dev/null | head -5; iptables -t nat -L -n 2>/dev/null | head -5 && echo '--INIT--' && "
            "cat /etc/inittab 2>/dev/null | head -5 || echo no-inittab ; "
            "ls /etc/init.d/ 2>/dev/null | head -20 || echo no-init-d",
            timeout=10, get_pty=True)
        time.sleep(3)
        out = b""
        while stdout.channel.recv_ready():
            out += stdout.channel.recv(4096)
        try:
            out += stdout.read()
        except:
            pass
        print(f"LOGIN: {user}:{pw} ✓")
        print(out.decode(errors="replace"))
        c.close()
        break
    except Exception as e:
        print(f"LOGIN: {user}:{pw} ✗ ({e})")
