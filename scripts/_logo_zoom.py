"""放大渲染原图关键区域，确认淡色残留(边框线/阴影)与图形本体的边界"""
from PIL import Image
import numpy as np

im = Image.open("c:/my_project/TUN_NAT_HUB/logo.png").convert("L")
a = np.array(im)
H, W = a.shape

chars = " .:-=+*#%@"
def char(v):
    idx = min(9, int((255 - v) / 256 * 10))
    return chars[idx]

def render_region(x0, x1, y0, y1, step=2, label=""):
    print(f"--- {label} x[{x0},{x1}] y[{y0},{y1}] step={step} ---")
    for y in range(y0, y1, step):
        row = "".join(char(a[y, x]) for x in range(x0, x1, step))
        print(row)
    print()

# 1. 左边 x40-140 区域，看 x=55 附近的淡线
render_region(40, 145, 250, 380, 2, "左边缘(找x55淡线)")
# 2. 右边 x1150-1254
render_region(1150, 1254, 250, 380, 2, "右边缘(找x1201淡线)")
# 3. 底部 y1100-1254 看阴影与图形分界
render_region(150, 1100, 1100, 1254, 4, "底部(找阴影带)")
# 4. 顶部 y35-60 看淡点
render_region(250, 1000, 35, 60, 3, "顶部(找淡点)")
