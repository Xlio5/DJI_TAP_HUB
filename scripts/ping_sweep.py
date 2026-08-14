#!/usr/bin/env python3
"""快速 ping 扫描局域网设备 — 多线程并发"""

import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

def ping_one(ip: str, timeout: float = 0.5) -> str | None:
    try:
        proc = subprocess.run(
            ["ping", "-n", "1", "-w", str(int(timeout * 1000)), ip],
            capture_output=True, timeout=timeout + 0.5,
        )
        if proc.returncode == 0:
            return ip
    except Exception:
        pass
    return None

def sweep(subnet: str, workers: int = 100) -> list[str]:
    print(f"\n{'='*50}")
    print(f"Scanning {subnet}.0/24 ...")
    print(f"{'='*50}")

    ips = [f"{subnet}.{i}" for i in range(1, 255)]
    found = []

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(ping_one, ip): ip for ip in ips}
        for fut in as_completed(futures):
            result = fut.result()
            if result:
                found.append(result)
                print(f"  [UP] {result}")

    print(f"--- {subnet}.0/24: {len(found)} host(s)")
    return sorted(found, key=lambda ip: [int(x) for x in ip.split(".")])

if __name__ == "__main__":
    targets = sys.argv[1:] if len(sys.argv) > 1 else ["192.168.144", "192.168.144"]
    all_found = {}
    for s in targets:
        all_found[s] = sweep(s)

    print(f"\n{'='*50}")
    print("Summary")
    print(f"{'='*50}")
    for subnet, hosts in all_found.items():
        label = f"{subnet}.0/24"
        if hosts:
            print(f"  {label}: {len(hosts)} host(s) — {', '.join(hosts)}")
        else:
            print(f"  {label}: none")
