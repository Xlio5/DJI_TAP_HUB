"""读回 SPI 镜像验证 U-Boot 段 bootcmd 内容"""
p = r"c:\my_project\TUN_NAT_HUB\backup\spi_image_v147.bin"
d = open(p, "rb").read()

UBOOT_OFF, UBOOT_LEN = 0x8000, 404384
seg = d[UBOOT_OFF:UBOOT_OFF + UBOOT_LEN]

print("镜像总长:", len(d))
print("U-Boot 段含 gpio input PB6 :", b"gpio input PB6" in seg)
print("U-Boot 段含 console=ttyS0,115200:", b"console=ttyS0,115200" in seg)
print("U-Boot 段含 console=null     :", b"console=null" in seg)
print("U-Boot 段含 console=ttyS0,921600:", b"console=ttyS0,921600" in seg)
print("rootfs magic hsqs:", d[0x710000:0x710004] == b"hsqs")

# 提取 bootcmd 字符串片段
import re
m = re.search(rb"bootcmd=if gpio input PB6[^\0]*", seg)
print("\nbootcmd 片段:")
print(m.group(0).decode(errors="replace") if m else "未找到")
