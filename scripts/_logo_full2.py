"""可读宽度的精细渲染：step=12 -> ~105 列"""
from PIL import Image
import numpy as np

im = Image.open("c:/my_project/TUN_NAT_HUB/logo.png").convert("L")
a = np.array(im)
H, W = a.shape

step = 12
chars = " .:-=+*#%@"
def char(v):
    idx = min(9, int((255 - v) / 256 * 10))
    return chars[idx]

for y in range(0, H, step):
    row = "".join(char(a[y, x]) for x in range(0, W, step))
    print(f"{y:4d}|{row}")
