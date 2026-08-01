"""回读校验：确认 mipmap 里的图标 = staging 生成的新图标（按像素比对）"""
from PIL import Image
import numpy as np
import os

stage = "c:/my_project/TUN_NAT_HUB/output/logo_icon"
res = "c:/my_project/TUN_NAT_HUB/android/app/src/main/res"
sizes = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}

print("=== 写后回读校验 ===")
all_ok = True
for dpi, sz in sizes.items():
    staged = Image.open(os.path.join(stage, f"ic_launcher_{dpi}.png")).convert("RGBA")
    written = Image.open(os.path.join(res, f"mipmap-{dpi}", "ic_launcher.png")).convert("RGBA")
    sa, wa = np.array(staged), np.array(written)
    dims_ok = sa.shape == wa.shape
    # 像素比对
    if dims_ok:
        diff = np.abs(sa.astype(int) - wa.astype(int)).sum()
        identical = diff == 0
    else:
        identical = False
    # 四角透明
    corners = [int(wa[1, 1, 3]), int(wa[-2, 1, 3]), int(wa[1, -2, 3]), int(wa[-2, -2, 3])]
    # 内容占比
    b = wa[..., 3] > 8
    yy, xx = np.where(b)
    bw, bh = int(xx.max()) - int(xx.min()) + 1, int(yy.max()) - int(yy.min()) + 1
    print(f"{dpi:6s}: 尺寸{dims_ok} 与staging逐像素一致={identical} 内容bbox={bw}x{bh} 四角alpha={corners}")
    if not (dims_ok and identical):
        all_ok = False

print("\n结果:", "全部一致 ✅" if all_ok else "有不一致 ❌")
