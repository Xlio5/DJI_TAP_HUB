"""
reboot_test.py — 上传修复脚本 → 重启 → 验证 → 循环直到稳定
"""
import paramiko, base64, time, os, sys

WIFI = "172.24.91.129"
WIRED = "192.168.88.66"

def colored(text, color):
    colors = {"G": "\033[92m", "R": "\033[91m", "Y": "\033[93m", "B": "\033[1m", "X": "\033[0m"}
    return colors.get(color, "") + text + colors["X"]

def ssh_connect(ip, timeout=10):
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(ip, username="xlong", password="1234", timeout=timeout)
    return c

def upload_files(c):
    with open(r"c:\my_project\TUN_NAT_HUB\scripts\cold_boot_fix.sh", "rb") as f:
        data = f.read().replace(b"\r\n", b"\n")
    b64 = base64.b64encode(data).decode()
    ch = c.get_transport().open_session()
    ch.exec_command("base64 -d > /home/xlong/cold_boot_fix.sh")
    ch.sendall(b64.encode())
    ch.shutdown_write()
    ch.recv_exit_status()
    ch.close()
    stdin, stdout, stderr = c.exec_command("chmod +x /home/xlong/cold_boot_fix.sh")
    stdout.read()
    return True

MAX_ROUNDS = 5
for round_num in range(1, MAX_ROUNDS + 1):

    print("\n" + "=" * 60)
    print("  Round %d" % round_num)
    print("=" * 60)

    # Step 1: Connect via current IP and upload + reboot
    connected = False
    for ip in [WIRED, WIFI]:
        try:
            c = ssh_connect(ip)
            connected = True
            print("  [ssh] %s" % ip)
            break
        except:
            continue

    if not connected:
        print("  [FATAL] Cannot connect")
        sys.exit(1)

    upload_files(c)

    # Reboot
    stdin, stdout, stderr = c.exec_command("echo 1234 | sudo -S reboot 2>/dev/null &", timeout=3)
    stdout.read()
    time.sleep(1)
    c.close()

    # Wait 95s
    print("  [wait] 95s...")
    for i in range(95, 0, -10):
        time.sleep(10)
        print("    %ds..." % i, end="\r")
    print()

    # Step 2: Reconnect and run fix
    ssh_ip = None
    for ip in [WIRED, WIFI]:
        try:
            c = ssh_connect(ip)
            ssh_ip = ip
            break
        except:
            continue

    if not ssh_ip:
        print("  [FATAL] Cannot reconnect after reboot")
        continue

    print("  [ssh] %s" % ssh_ip)

    # Run fix script
    stdin, stdout, stderr = c.exec_command(
        "echo 1234 | sudo -S bash /home/xlong/cold_boot_fix.sh",
        timeout=30, get_pty=True)
    out = b""
    t0 = time.time()
    while time.time() - t0 < 25:
        if stdout.channel.recv_ready():
            out += stdout.channel.recv(4096)
        if stdout.channel.exit_status_ready():
            break
        time.sleep(0.2)
    try:
        out += stdout.read()
    except:
        pass

    text = out.decode(errors="replace")
    # Print key lines
    all_ok = False
    for line in text.split("\n"):
        line = line.strip()
        if not line:
            continue
        if "ALL_OK" in line:
            print("  [PASS] ALL OK!")
            all_ok = True
        elif "SOME_FAILED" in line:
            print("  [FAIL] Some checks failed")
        elif "RESULT:" in line:
            print("  " + line)
        elif "FIXED:" in line:
            print("  [fixed]" + line.replace("FIXED:", ""))
        elif "FAILED:" in line:
            print("  [still]" + line.replace("FAILED:", ""))

    # Print full text for debugging failed rounds
    if not all_ok:
        # Print all lines
        for line in text.split("\n"):
            line = line.strip()
            if line and "password" not in line.lower():
                print("    " + line)

    c.close()

    if all_ok:
        print("\n" + "=" * 60)
        print("  SUCCESS after %d rounds!" % round_num)
        print("=" * 60)
        break

print("\nTest complete.")
