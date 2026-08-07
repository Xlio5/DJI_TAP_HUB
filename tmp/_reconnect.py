"""重试连接设备, 观察是否可达/重启中"""
import paramiko, time, socket

def ping_port(host, port, t=3):
    try:
        s = socket.create_connection((host, port), timeout=t)
        s.close()
        return True
    except Exception:
        return False

print("=== 设备可达性轮询 (最多 60s) ===")
t0 = time.time()
for i in range(20):
    ok = ping_port("192.168.144.66", 22)
    print(f"[{i+1}] t+{time.time()-t0:.0f}s SSH: {'可达' if ok else '不可达'}")
    if ok:
        break
    time.sleep(3)
print("\n[done]")
