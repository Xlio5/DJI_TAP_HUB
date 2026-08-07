"""验证 SPI 镜像 env 区 (0x7E000) 与 bootcmd 一致性"""
p = r"c:\my_project\TUN_NAT_HUB\backup\spi_image_v147.bin"
d = open(p, "rb").read()
env = d[0x7E000:0x7E000 + 0x2000]

print("env 区含 gpio input PB6:", b"gpio input PB6" in env)
print("env 区含 console=ttyS0,115200:", b"console=ttyS0,115200" in env)
print("env 区含 console=null:", b"console=null" in env)
print("env 区含 root=/dev/mtdblock3:", b"root=/dev/mtdblock3" in env)
print("env 区含 921600:", b"921600" in env)
# CRC
import binascii
body = env[:0x1FFC]
crc = binascii.crc32(body) & 0xFFFFFFFF
stored = int.from_bytes(env[0x1FFC:0x2000], "little")
print(f"env CRC: 计算=0x{crc:08X} 存储=0x{stored:08X} {'一致' if crc == stored else '不一致'}")
