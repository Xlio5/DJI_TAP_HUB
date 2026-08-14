#!/usr/bin/env python3
"""全子网扫描 RTSP (554) + HTTP (80) 端口，找摄像头"""

import socket
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

def check_port(ip: str, port: int, timeout: float = 0.5) -> str | None:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        if s.connect_ex((ip, port)) == 0:
            s.close()
            return f"{ip}:{port}"
        s.close()
    except Exception:
        pass
    return None

def sweep_subnet(subnet: str, ports: list[int], workers: int = 200):
    print(f"\n{'='*50}")
    print(f"Sweep {subnet}.0/24 ports:{ports}")
    print(f"{'='*50}")
    found = {}
    for port in ports:
        found[port] = []

    for port in ports:
        ips = [f"{subnet}.{i}" for i in range(1, 255)]
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {pool.submit(check_port, ip, port): ip for ip in ips}
            for fut in as_completed(futures):
                r = fut.result()
                if r:
                    found[port].append(r)
                    print(f"  [OPEN] {r}")

    return found

if __name__ == "__main__":
    targets = sys.argv[1:] if len(sys.argv) > 1 else ["192.168.144", "192.168.144"]
    ports = [554, 80, 8080, 8000, 8554, 443]
    for s in targets:
        result = sweep_subnet(s, ports)
        for port, hosts in result.items():
            if hosts:
                print(f"\n  {port}: {hosts}")
