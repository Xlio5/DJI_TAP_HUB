"""Quick port scan of V3s."""
import socket
for p in [22, 23, 80, 2222, 8080, 873, 111]:
    s = socket.socket()
    s.settimeout(2)
    r = s.connect_ex(("192.168.88.66", p))
    print(f"port {p}: {'OPEN' if r == 0 else 'closed'}")
    s.close()
