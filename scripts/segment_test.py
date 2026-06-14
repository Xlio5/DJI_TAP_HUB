"""Segment latency test: deploy echo server + compile UDP ping for DJI RC."""
import paramiko, base64, subprocess, time, sys, os, tempfile
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HOST = "192.168.88.66"
DJI = "172.24.91.112:33625"

# ══════════════════════════════════════════════
# Step 1: Deploy UDP echo server on RK3588
# ══════════════════════════════════════════════
print("=" * 60)
print("Step 1: Deploy UDP echo server on RK3588 (10.0.0.1:9999)")
print("=" * 60)

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect(HOST, username="xlong", password="1234", timeout=10)
S = "echo '1234' | sudo -S"

def ssh(cmd, timeout=10):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=timeout)
    out = stdout.read().decode(errors="replace")
    if out.strip(): print(out.strip())

ssh("killall -9 python3 2>/dev/null; true")
time.sleep(0.3)

server_code = """import socket
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("10.0.0.1", 9999))
print("READY", flush=True)
while True:
    data, addr = s.recvfrom(2048)
    s.sendto(data, addr)
"""

b64 = base64.b64encode(server_code.encode()).decode()
cmd = "python3 -c 'import base64,sys; d=base64.b64decode(sys.stdin.read()); open(\"/home/xlong/echo_srv.py\",\"w\").write(d.decode()); print(\"OK\")'"
transport = c.get_transport()
chan = transport.open_session()
chan.exec_command(cmd)
chan.sendall(b64.encode())
chan.shutdown_write()
chan.recv_exit_status()
chan.close()
ssh("nohup python3 /home/xlong/echo_srv.py > /home/xlong/echo_out.txt 2>&1 & echo STARTED")
time.sleep(1)
ssh("ss -tulnp 2>/dev/null | grep 9999")

# ══════════════════════════════════════════════
# Step 2: Compile UDP ping to DEX for DJI RC
# ══════════════════════════════════════════════
print("\n" + "=" * 60)
print("Step 2: UDP Ping test - USB tunnel RTT")
print("=" * 60)

udp_ping_java = """import java.net.*;
import java.nio.*;

public class UdpPing {
    public static void main(String[] args) throws Exception {
        int n = args.length > 0 ? Integer.parseInt(args[0]) : 50;
        String host = args.length > 1 ? args[1] : "10.0.0.1";
        int port = args.length > 2 ? Integer.parseInt(args[2]) : 9999;

        DatagramSocket s = new DatagramSocket();
        s.setSoTimeout(3000);
        InetSocketAddress server = new InetSocketAddress(host, port);
        ByteBuffer bb = ByteBuffer.allocate(20);

        double[] rtts = new double[n];
        int drp = 0;

        for (int i = 0; i < n; i++) {
            bb.clear();
            long t0 = System.nanoTime();
            bb.putLong(t0);
            DatagramPacket pkt = new DatagramPacket(bb.array(), bb.position(), server);
            s.send(pkt);
            try {
                DatagramPacket resp = new DatagramPacket(new byte[256], 256);
                s.receive(resp);
                long t1 = System.nanoTime();
                ByteBuffer rb = ByteBuffer.wrap(resp.getData());
                long sent = rb.getLong();
                rtts[i - drp] = (t1 - sent) / 1_000_000.0;
            } catch (SocketTimeoutException e) {
                drp++;
            }
        }
        s.close();

        java.util.Arrays.sort(rtts, 0, n - drp);
        double sum = 0;
        for (int i = 0; i < n - drp; i++) sum += rtts[i];
        int valid = n - drp;
        if (valid == 0) { System.out.println("ALL_DROPPED"); return; }
        double avg = sum / valid;
        int i50 = valid / 2;
        int i95 = (int)(valid * 0.95);
        int i99 = valid > 10 ? (int)(valid * 0.99) : valid - 1;

        System.out.printf("USB-TUNNEL-RTT n=%d dropped=%d avg=%.2fms p50=%.2fms p95=%.2fms p99=%.2fms min=%.2fms max=%.2fms%n",
            n, drp, avg, rtts[i50], rtts[i95], rtts[i99], rtts[0], rtts[valid-1]);
    }
}
"""

# Write Java, compile, dex, push
tmp = tempfile.gettempdir()
java_file = os.path.join(tmp, "UdpPing.java")
with open(java_file, "w") as f:
    f.write(udp_ping_java)

out_dir = os.path.join(tmp, "udpping_out")
os.makedirs(out_dir, exist_ok=True)

java_home = "C:\\Program Files\\Java\\jdk-17.0.18"
sdk = os.path.join(os.environ["LOCALAPPDATA"], "Android", "Sdk")
d8 = os.path.join(sdk, "build-tools", "35.0.0", "d8.bat")

# Compile
r = subprocess.run([os.path.join(java_home, "bin", "javac.exe"), "-d", out_dir, java_file],
                   capture_output=True, text=True)
if r.returncode != 0:
    print("javac ERR:", r.stderr)
    sys.exit(1)

# dex
dex_out = os.path.join(tmp, "udpping_dex")
os.makedirs(dex_out, exist_ok=True)
r = subprocess.run([d8, "--output", dex_out, os.path.join(out_dir, "UdpPing.class")],
                   capture_output=True, text=True)
if r.returncode != 0:
    print("d8 ERR:", r.stderr)
    sys.exit(1)

# push
subprocess.run(["adb", "-s", DJI, "push", os.path.join(dex_out, "classes.dex"),
                "/sdcard/udpping.dex"], capture_output=True)

# ══════════════════════════════════════════════
# Step 3: Run tests
# ══════════════════════════════════════════════
print("\n" + "=" * 60)
print("Step 3: USB Tunnel RTT (DJI RC -> 10.0.0.1 -> echo -> back)")
print("=" * 60)

r = subprocess.run(["adb", "-s", DJI, "shell",
                    "CLASSPATH=/sdcard/udpping.dex app_process /system/bin UdpPing 50 10.0.0.1 9999 2>&1"],
                   capture_output=True, text=True, timeout=120)
print(r.stdout.strip())
if r.stderr.strip():
    print("[err]", r.stderr.strip()[:200])

# ══════════════════════════════════════════════
# Step 4: Camera RTT from RK3588
# ══════════════════════════════════════════════
print("\n" + "=" * 60)
print("Step 4: RK3588 -> Camera RTT (LAN)")
print("=" * 60)
ssh("ping -c 10 192.168.88.101 2>&1")

# ══════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════
print("\n" + "=" * 60)
print("Latency Breakdown")
print("=" * 60)
print("USB Tunnel  = <step 3 result>  (our tunnel A)")
print("Camera LAN  = <step 4 result>  (RK3588 -> camera B)")
print("Total (A+B) = USB + Camera    (network part)")
print("Video delay = your measured 330ms - (A+B) = codec/player overhead")
c.close()
