import paramiko, time
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=10, allow_agent=False, look_for_keys=False, banner_timeout=8)
def r(cmd):
    _, out, _ = c.exec_command(cmd); time.sleep(0.3)
    return out.read().decode(errors="replace")

print("=== cmdline ===")
print(r("cat /proc/cmdline"))

print("=== dji_rc running? ===")
out = r("ps | grep dji_rc | grep -v grep || echo NOT_RUNNING")
print(out)

print("=== start services ===")
r("killall dji_rc uart_echo 2>/dev/null; sleep 0.3")
r("/usr/local/bin/dji_rc > /var/log/dji_rc.log 2>&1 &")
r("/usr/local/bin/web_server > /var/log/web_server.log 2>&1 &")
r("/usr/local/bin/usb_tund > /var/log/usb_tund.log 2>&1 &")
time.sleep(1.5)
out = r("ps | grep -E 'dji_rc|web_server|usb_tund' | grep -v grep || echo none")
print(out)

print("=== dji_rc log ===")
print(r("head -10 /var/log/dji_rc.log 2>/dev/null || echo NO_LOG"))

# upload uart_echo
chan = c.get_transport().open_session()
chan.exec_command("cat > /var/log/ue")
with open(r"c:\my_project\TUN_NAT_HUB\scripts\uart_echo", "rb") as f:
    data = f.read()
chan.sendall(data); chan.shutdown_write()
chan.close()
r("chmod 755 /var/log/ue")

# kill dji_rc, start echo
r("killall dji_rc 2>/dev/null; sleep 0.3")
r("/var/log/ue /dev/ttyS1 921600 > /dev/null 2>&1 &")
time.sleep(0.3)
pid = r("ps | grep '/var/log/ue' | grep -v grep").strip()
print()
print("=== ttyS1 @921600 回环就绪, PID=" + pid + " ===")
c.close()
