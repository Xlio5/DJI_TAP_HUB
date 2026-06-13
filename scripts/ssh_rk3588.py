#!/usr/bin/env python3
"""SSH client for RK3588 - build & deploy ECM/RNDIS daemon.
Transfers files via stdin pipe; uses sudo -S for admin commands.
"""

import paramiko, sys, os, base64, time

HOST = "172.24.91.28"
PORT = 22
USER = "xlong"
PWD = "1234"
SUDO_PREFIX = f"echo '{PWD}' | sudo -S "

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REMOTE_DIR = "/home/xlong/tun_nat_hub"


def ssh_exec(ssh, cmd, timeout=30):
    """Execute a command, return (stdout, exit_code)."""
    print(f"[RK3588] $ {cmd}")
    stdin, stdout, stderr = ssh.exec_command(cmd, timeout=timeout, get_pty=True)
    out = stdout.read().decode()
    err = stderr.read().decode()
    code = stdout.channel.recv_exit_status()
    if out.strip():
        print(out.strip())
    if err.strip():
        print(f"[stderr] {err.strip()}")
    return out, code


def upload_file_b64(ssh, local_rel, remote_path):
    """Upload a file by piping base64 data through stdin to remote python."""
    local_path = os.path.join(PROJECT_ROOT, local_rel)
    with open(local_path, 'rb') as f:
        data = f.read()
    b64 = base64.b64encode(data).decode()

    print(f"  PUT {local_rel} ({len(b64)} chars b64)")
    parent = os.path.dirname(remote_path)
    ssh_exec(ssh, f"mkdir -p {parent}")

    # Pipe b64 through stdin to remote python
    cmd = f"python3 -c \"import base64,sys; open('{remote_path}','wb').write(base64.b64decode(sys.stdin.read()))\""
    transport = ssh.get_transport()
    if transport is None or not transport.is_active():
        print("  WARNING: SSH transport lost")
        return False

    chan = transport.open_session()
    chan.exec_command(cmd)
    chan.sendall(b64.encode())
    chan.shutdown_write()
    exit_code = chan.recv_exit_status()
    chan.close()

    if exit_code != 0:
        print(f"  WARNING: upload failed (exit {exit_code})")
        return False

    # Verify
    out, _ = ssh_exec(ssh, f"wc -c < '{remote_path}'")
    try:
        size = int(out.strip())
        expected = len(data)
        ok = "OK" if size == expected else f"MISMATCH {size}!={expected}"
        print(f"  {ok}")
        return size == expected
    except ValueError:
        print("  ?")
        return False


def main():
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    try:
        print(f"Connecting to {USER}@{HOST}...")
        ssh.connect(HOST, port=PORT, username=USER, password=PWD, timeout=15)
        print("Connected!")

        # 1. Setup build env
        ssh_exec(ssh, f"mkdir -p /home/xlong/tmp")
        ssh_exec(ssh, f"rm -rf /tmp/* 2>/dev/null || true")

        # 2. Upload source files
        print("\n--- Uploading source files ---")
        files = [
            ("ubuntu/CMakeLists.txt", f"{REMOTE_DIR}/ubuntu/CMakeLists.txt"),
            ("ubuntu/src/main.cpp", f"{REMOTE_DIR}/ubuntu/src/main.cpp"),
            ("ubuntu/src/tun_iface.h", f"{REMOTE_DIR}/ubuntu/src/tun_iface.h"),
            ("ubuntu/src/tun_iface.cpp", f"{REMOTE_DIR}/ubuntu/src/tun_iface.cpp"),
            ("ubuntu/scripts/setup_gadget.sh", f"{REMOTE_DIR}/ubuntu/scripts/setup_gadget.sh"),
            ("ubuntu/scripts/setup_nat.sh", f"{REMOTE_DIR}/ubuntu/scripts/setup_nat.sh"),
            ("ubuntu/config/tun_nat_hub.service", f"{REMOTE_DIR}/ubuntu/config/tun_nat_hub.service"),
        ]
        for local_rel, remote_path in files:
            if not upload_file_b64(ssh, local_rel, remote_path):
                print(f"Upload FAILED for {local_rel}, continuing anyway...")

        # 3. Build
        print("\n--- Building ---")
        build_cmd = (
            f"export TMPDIR=/home/xlong/tmp; "
            f"cd {REMOTE_DIR}/ubuntu && rm -rf build && "
            f"cmake -B build -DCMAKE_BUILD_TYPE=Release 2>&1 && "
            f"cmake --build build -- -j$(nproc) 2>&1"
        )
        out, code = ssh_exec(ssh, build_cmd, timeout=120)
        if code != 0:
            print(f"Build FAILED (exit {code})")
            return 1

        # 4. Verify
        ssh_exec(ssh, f"file {REMOTE_DIR}/ubuntu/build/usb_tund")
        ssh_exec(ssh, f"ls -lh {REMOTE_DIR}/ubuntu/build/usb_tund")

        # 5. Install (with sudo -S)
        print("\n--- Installing ---")
        S = SUDO_PREFIX
        ssh_exec(ssh, f"{S} cp {REMOTE_DIR}/ubuntu/build/usb_tund /usr/local/bin/usb_tund")
        ssh_exec(ssh, f"{S} chmod +x /usr/local/bin/usb_tund")
        ssh_exec(ssh, f"{S} cp {REMOTE_DIR}/ubuntu/scripts/setup_gadget.sh /usr/local/bin/setup_gadget.sh")
        ssh_exec(ssh, f"{S} cp {REMOTE_DIR}/ubuntu/scripts/setup_nat.sh /usr/local/bin/setup_nat.sh")
        ssh_exec(ssh, f"{S} chmod +x /usr/local/bin/setup_gadget.sh /usr/local/bin/setup_nat.sh")
        ssh_exec(ssh, f"{S} cp {REMOTE_DIR}/ubuntu/config/tun_nat_hub.service /etc/systemd/system/tun_nat_hub.service")

        # 6. Reload systemd, stop old service (ignore errors)
        print("\n--- Reloading systemd ---")
        ssh_exec(ssh, f"{S} systemctl daemon-reload")
        # Kill any running instance first (so we can overwrite binary)
        ssh_exec(ssh, f"{S} killall usb_tund 2>/dev/null; {S} systemctl stop tun_nat_hub 2>/dev/null; true", timeout=10)
        time.sleep(1)

        # Re-copy binary now that it's not busy
        ssh_exec(ssh, f"{S} cp {REMOTE_DIR}/ubuntu/build/usb_tund /usr/local/bin/usb_tund")

        # 7. Run gadget + nat setup
        print("\n--- ECM Gadget Setup ---")
        ssh_exec(ssh, f"{S} /usr/local/bin/setup_gadget.sh", timeout=30)
        ssh_exec(ssh, f"{S} /usr/local/bin/setup_nat.sh", timeout=30)

        # 8. Start service
        print("\n--- Starting service ---")
        ssh_exec(ssh, f"{S} systemctl enable tun_nat_hub 2>&1", timeout=20)
        ssh_exec(ssh, f"{S} systemctl restart tun_nat_hub 2>&1", timeout=20)
        time.sleep(3)

        # 9. Status summary
        print("\n=== Service Status ===")
        ssh_exec(ssh, f"{S} systemctl status tun_nat_hub --no-pager -l 2>&1 | head -20")
        print("\n=== USB Interfaces ===")
        ssh_exec(ssh, "ip link show 2>&1 | grep -E 'usb|rndis'")
        print("\n=== Daemon Logs ===")
        ssh_exec(ssh, f"{S} journalctl -u tun_nat_hub --no-pager -n 20 2>&1")

        ssh.close()
        print("\n=== Deployment Complete ===")
        return 0

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
