"""ASCII 渲染 ic_launcher.png(看当前 app 图标实际结构)+ 检查 logo 白色卡片是否有阴影边缘"""
from PIL import Image
import numpy as np

def ascii_view(name, W=48):
    im = Image.open(name).convert("RGBA")
    a = np.array(im)
    # 渲染用合成: 半透明区域显示为 '.' 边框, 不透明显示灰度, 完全透明显示空格
    rgb = a[..., :3].mean(axis=2)
    alpha = a[..., 3]
    sm_rgb = Image.fromarray(rgb.astype(np.uint8)).resize((W, W), Image.LANCZOS)
    sm_alpha = Image.fromarray(alpha.astype(np.uint8)).resize((W, W), Image.LANCZOS)
    g = np.array(sm_rgb)
    al = np.array(sm_alpha)
    chars = " .:-=+*#%@"
    print(f"== {name} ({im.size}) ==")
    for y in range(W):
        row = ""
        for x in range(W):
            if al[y, x] < 40:
                row += " "
            elif al[y, x] < 200:
                row += "."
            else:
                idx = min(9, int((255 - g[y, x]) / 256 * 10))
                row += chars[idx]
        print(row)
    print()

ascii_view("c:/my_project/TUN_NAT_HUB/android/app/src/main/res/mipmap-xxxhdpi/ic_launcher.png")

# 检查 logo 卡片边缘是否有阴影: 沿对角线从中心向外扫描灰度变化
im = Image.open("c:/my_project/TUN_NAT_HUB/logo.png").convert("L")
a = np.array(im)
h, w = a.shape
# 从中心 (w//2, h//2) 沿水平线向右扫, 打印每 10px 的灰度, 找卡片边缘
print("logo.png 沿水平中线向右扫描的灰度 (y=h/2):")
cx, cy = w // 2, h // 2
for x in range(cx, w, 8):
    print(f"  x={x}: {a[cy, x]}")
# 沿垂直中线向下扫描
print("logo.png 沿垂直中线向下扫描的灰度 (x=w/2):")
for y in range(cy, h, 8):
    print(f"  y={y}: {a[y, cx]}")
