"""生成缩小预览 + 定位非白色内容包围盒，确认 logo 实际内容范围"""
from PIL import Image
import numpy as np

src = "c:/my_project/TUN_NAT_HUB/logo.png"
im = Image.open(src).convert("RGBA")
a = np.array(im).astype(int)

# 与白色(255)的距离
dist = np.abs(a[..., :3] - 255).sum(axis=2)  # 每像素与白色的 RGB 差之和

# 统计各灰度的分布，判断 logo 是深色还是浅色
hist, _ = np.histogram(dist, bins=[0, 2, 10, 30, 100, 300, 766])
labels = ["纯白(<2)", "近白(2-10)", "淡灰(10-30)", "中灰(30-100)", "深灰(100-300)", "深色(>300)"]
for l, c in zip(labels, hist):
    pct = 100.0 * c / dist.size
    print(f"  {l}: {c} 像素 ({pct:.1f}%)")

# 找出非白内容包围盒
for thr in [30, 100, 300]:
    mask = dist > thr
    if mask.any():
        ys, xs = np.where(mask)
        print(f"  dist>{thr} bbox: x[{xs.min()},{xs.max()}] y[{ys.min()},{ys.max()}]  (宽{xs.max()-xs.min()+1} 高{ys.max()-ys.min()+1})")
    else:
        print(f"  dist>{thr}: 无")

# 缩小到 300x300 保存预览（放大内容区域对比度）
im_small = im.resize((300, 300), Image.LANCZOS)
im_small.save("c:/my_project/TUN_NAT_HUB/scripts/_logo_preview.png")
print("preview saved")

# 如果内容太浅，也保存一张自动对比度增强的版本
g = a[..., :3].mean(axis=2)
lo, hi = np.percentile(g[g < 250], [2, 98]) if (g < 250).sum() else (0, 255)
print(f"  non-white gray percentile 2/98: {lo:.1f} / {hi:.1f}")
