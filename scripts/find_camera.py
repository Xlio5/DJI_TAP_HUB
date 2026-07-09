#!/usr/bin/env python3
"""扫描指定 IP 的常用摄像头端口"""

import socket
import sys
from concurrent.futures import ThreadPoolExecutor

CAMERA_PORTS = [80, 443, 554, 1935, 8000, 8080, 8554, 3702, 8899, 34567]

def check_port(ip: str, port: int, timeout: float = 1.0) -> int | None:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        if s.connect_ex((ip, port)) == 0:
            s.close()
            return port
        s.close()
    except Exception:
        pass
    return None

def scan_ip(ip: str) -> dict:
    print(f"\nScanning {ip} ...")
    open_ports = []
    with ThreadPoolExecutor(max_workers=20) as pool:
        futures = {pool.submit(check_port, ip, p): p for p in CAMERA_PORTS}
        for fut in futures:
            port = fut.result()
            if port:
                open_ports.append(port)
                print(f"  [OPEN] {ip}:{port}")
    return {"ip": ip, "ports": sorted(open_ports)}

if __name__ == "__main__":
    targets = sys.argv[1:] if len(sys.argv) > 1 else ["192.168.144.88", "192.168.88.88"]
    for t in targets:
        result = scan_ip(t)
        if not result["ports"]:
            print(f"  No open ports found")
        else:
            print(f"  => {result['ip']} ports: {result['ports']}")
