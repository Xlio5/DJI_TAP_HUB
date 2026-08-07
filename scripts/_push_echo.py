import paramiko, time, base64
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False, banner_timeout=10)
def r(cmd):
    _, out, _ = c.exec_command(cmd); time.sleep(0.1)
    return out.read().decode(errors="replace")

r("killall dji_rc uart_echo 2>/dev/null; sleep 0.3")
r("rm -f /var/log/ue.b64")

with open(r"c:\my_project\TUN_NAT_HUB\scripts\uart_echo", "rb") as f:
    data = f.read()
b64 = base64.b64encode(data).decode()
total = len(data)
CHUNK = 2000
pieces = [b64[i:i + CHUNK] for i in range(0, len(b64), CHUNK)]
n = len(pieces)
print("Uploading {0} bytes in {1} chunks...".format(total, n))

for i, part in enumerate(pieces):
    safe = part.replace("'", "'\"'\"'")
    r("printf '%s' '{0}' >> /var/log/ue.b64".format(safe))
    if i % 40 == 0:
        print("  {0}/{1}".format(i, n))

print("decoding...")
r("base64 -d /var/log/ue.b64 > /var/log/uart_echo 2>/dev/null")
sz = r("wc -c /var/log/uart_echo 2>/dev/null || echo 0")
print("decoded size: {0} (expected {1})".format(sz.strip(), total))

actual = int(sz.strip().split()[0]) if sz.strip() and sz.strip().split()[0].isdigit() else 0
if actual == total:
    r("chmod 755 /var/log/uart_echo")
    r("/var/log/uart_echo /dev/ttyS1 921600 > /dev/null 2>&1 &")
    time.sleep(0.5)
    pid = r("ps | grep uart_echo | grep -v grep").strip()
    print("PID: " + pid)
    print("=== ttyS1 @921600 回环已就绪 ===")
    print("PC串口助手连 PE21(RX)/PE22(TX) @921600 8N1, 发送数据测试!")
c.close()
