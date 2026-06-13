"""Quick fix: change RK3588 usb0 IP to match DJI RC subnet."""
import paramiko

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("172.24.91.28", username="xlong", password="1234", timeout=10)

def run(cmd):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=10)
    out = stdout.read().decode()
    err = stderr.read().decode()
    if out.strip(): print(out.strip())
    if err.strip(): print("[e]", err.strip())

S = "echo '1234' | sudo -S"
run(f"{S} ip addr del 10.0.0.1/24 dev usb0 2>/dev/null; echo ok1")
run(f"{S} ip addr add 192.168.50.2/24 dev usb0; echo ok2")
run("ip addr show usb0 | grep inet")
c.close()
print("Done - now testing ping from DJI RC...")
