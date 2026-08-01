"""ASCII 渲染 logo,让我能"看到"logo 结构和圆角框位置"""
from PIL import Image
import numpy as np

src = "c:/my_project/TUN_NAT_HUB/logo.png"
im = Image.open(src).convert("L")
a = np.array(im)

# 缩到 64 宽,字符映射: 白->' ' 黑->'#'
W = 72
H = 72
sm = Image.fromarray(a).resize((W, H), Image.LANCZOS)
g = np.array(sm)

chars = " .:-=+*#%@"
def char(v):
    # v 0=黑, 255=白
    idx = min(9, int((255 - v) / 256 * 10))
    return chars[idx]

print("ASCII view (深色=logo内容, 空白=白色背景):")
for y in range(H):
    row = "".join(char(g[y, x]) for x in range(W))
    print(row)

# 同时输出每行/每列第一个非白像素位置,帮助确定圆角框边界
# 找非白(灰度<240)的行列范围
m = a < 240
if m.any():
    ys, xs = np.where(m)
    print(f"\n非白内容 bbox: x[{xs.min()},{xs.max()}] y[{ys.min()},{ys.max()}]")
    # 沿图像边缘扫描,找圆角框在白底上的边界
    # 在 y=2(顶部)一行,找左侧第一个非白
    for y_row in [2, 30, 60, 100, 200, 400, 600]:
        row = a[y_row]
        nz = np.where(row < 245)[0]
        if len(nz):
            print(f"  行 y={y_row}: 非白 x 范围 [{nz.min()},{nz.max()}]")
        else:
            print(f"  行 y={y_row}: 整行近白")
