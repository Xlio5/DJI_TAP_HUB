"""OTA 预检: web_server 8080 在线 + 端口可访问 + v149 rootfs 文件就绪"""
import socket, os, time

def tcp_ok(host, port, timeout=5):
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        s.close()
        return True
    except Exception as e:
        return f"{e}"

print("=== 1. web_server 8080 可达 ===")
print("192.168.144.66:8080 ->", tcp_ok("192.168.144.66", 8080))

print("\n=== 2. v149 rootfs 文件 ===")
p = r"c:\my_project\TUN_NAT_HUB\backup\rootfs_v149.squashfs"
print("存在:", os.path.exists(p))
print("大小:", os.path.getsize(p), "bytes")
print("magic:", open(p, "rb").read(4))
print("(web_server 校验: 需 1MB-8MB, magic hsqs)")

print("\n=== 3. v149 镜像 (备选) ===")
p2 = r"c:\my_project\TUN_NAT_HUB\backup\spi_image_v149.bin"
print("spi_image 存在:", os.path.exists(p2))
print("spi_image 大小:", os.path.getsize(p2) if os.path.exists(p2) else "N/A")
print("\n[done]")
