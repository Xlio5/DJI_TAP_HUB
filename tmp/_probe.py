"""探测设备各端口可达性"""
import socket, time

host = "192.168.144.66"
for port, name in [(22, "SSH"), (8080, "web_server"), (80, "http")]:
    try:
        s = socket.create_connection((host, port), timeout=5)
        s.close()
        print(f"{name} ({port}): 可达 ✓")
    except Exception as e:
        print(f"{name} ({port}): 不可达 ({e})")

# ping 测试
import subprocess
r = subprocess.run(["ping", "-n", "2", host], capture_output=True, text=True)
print("\nping:", "通" if "TTL" in r.stdout or "时间" in r.stdout else "不通")
