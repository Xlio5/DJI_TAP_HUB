"""精细渲染原图（阈值包含淡色），确定图形本体 vs 卡片装饰的边界"""
from PIL import Image
import numpy as np

im = Image.open("c:/my_project/TUN_NAT_HUB/logo.png").convert("L")
a = np.array(im)
H, W = a.shape
print(f"原图 {W}x{H}")

# 精细渲染：直接取样，不做平均下采样，step=3 约 W/3 列
step = 3
chars = " .:-=+*#%@"
def char(v):
    idx = min(9, int((255 - v) / 256 * 10))
    return chars[idx]

for y in range(0, H, step):
    row = "".join(char(a[y, x]) for x in range(0, W, step))
    # 只打印有内容的行(非全空格)
    if row.strip():
        print(f"{y:4d}|{row}")
