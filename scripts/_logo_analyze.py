"""分析 logo 图片的透明度和圆角结构，确定需要裁剪的边框范围"""
import sys
from PIL import Image
import numpy as np

def analyze(name):
    im = Image.open(name).convert("RGBA")
    a = np.array(im)
    print(f"== {name} ==")
    print(f"  size: {im.size}  mode: {im.mode}")
    alpha = a[..., 3]
    print(f"  alpha min/max/mean: {alpha.min()}/{alpha.max()}/{alpha.mean():.1f}")
    for label, thr in [("alpha>0", 1), ("alpha>10", 10), ("alpha>250", 250)]:
        mask = alpha > thr
        if mask.any():
            ys, xs = np.where(mask)
            print(f"  bbox({label}): x[{xs.min()},{xs.max()}] y[{ys.min()},{ys.max()}]  (宽{xs.max()-xs.min()+1} 高{ys.max()-ys.min()+1})")
        else:
            print(f"  bbox({label}): 空")
    w, h = im.size
    corners = {"TL": (3, 3), "TR": (w - 4, 3), "BL": (3, h - 4), "BR": (w - 4, h - 4)}
    for cn, (cx, cy) in corners.items():
        print(f"  corner {cn} ({cx},{cy}) RGBA={a[cy, cx].tolist()}")
    print(f"  center RGBA: {a[h // 2, w // 2].tolist()}")
    print()

for name in sys.argv[1:]:
    analyze(name)
