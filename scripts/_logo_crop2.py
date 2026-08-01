"""裁剪 logo.png 白色圆角卡片边框（含贴边阴影），只保留图形本体。

v2：白色抠透明 + 连通域分析，删除所有贴到画布边缘的残留组件（卡片阴影/灰边），
只保留中间的图形本体。
"""
from PIL import Image
import numpy as np
import cv2
import os

SRC = "c:/my_project/TUN_NAT_HUB/logo.png"
STAGE = "c:/my_project/TUN_NAT_HUB/output/logo_icon"
MIPMAPS = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}

im = Image.open(SRC).convert("RGBA")
a = np.array(im).astype(np.float32)
H, W = a.shape[:2]

dist = (255 - a[..., 0]) + (255 - a[..., 1]) + (255 - a[..., 2])
T_LOW, T_HIGH = 8.0, 30.0
alpha = np.clip((dist - T_LOW) / (T_HIGH - T_LOW), 0, 1) * 255
rgba = np.dstack([a[..., :3], alpha]).astype(np.uint8)

# 连通域分析（基于 alpha>40 的二值）
binmask = (alpha > 40).astype(np.uint8)
n, labels, stats, cents = cv2.connectedComponentsWithStats(binmask, connectivity=8)
print(f"连通域数量: {n-1}")

keep = np.zeros((H, W), bool)
for i in range(1, n):
    x, y, w, h, area = stats[i]
    touches_border = (x == 0) or (y == 0) or (x + w >= W) or (y + h >= H)
    cx, cy = cents[i]
    print(f"  comp{i}: area={area} bbox=[{x},{y},{x+w},{y+h}] 贴边={touches_border}")
    if not touches_border:
        keep |= (labels == i)

# 保护：如果没有任何非贴边组件，说明异常，中止
if not keep.any():
    raise SystemExit("错误：无非贴边组件，说明图形与贴边残留连在一起，中止避免误删。")

# 贴边残留的 alpha 归零（先膨胀一点吃掉软边缘）
border_region = (~keep).astype(np.uint8) * 255
dilated = cv2.dilate(border_region, np.ones((7, 7), np.uint8))
alpha_final = alpha * (dilated == 0).astype(np.float32)
out = np.dstack([a[..., :3], alpha_final]).astype(np.uint8)

# 裁剪到图形包围盒
mask = alpha_final > 8
ys, xs = np.where(mask)
x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
gw, gh = x1 - x0 + 1, y1 - y0 + 1
print(f"\n图形包围盒: x[{x0},{x1}] y[{y0},{y1}]  宽{gw} 高{gh}  宽高比{gw/gh:.3f}")

crop_im = Image.fromarray(out[y0:y1 + 1, x0:x1 + 1])

# 居中放方形透明画布，margin 使图形占边长 80%
margin = 0.10
canvas = int(max(gw, gh) / (1 - 2 * margin))

def place(art, size):
    c = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    aw = int(size * gw / max(gw, gh))
    ah = int(size * gh / max(gw, gh))
    art_resized = art.resize((aw, ah), Image.LANCZOS)
    c.paste(art_resized, ((size - aw) // 2, (size - ah) // 2), art_resized)
    return c

os.makedirs(STAGE, exist_ok=True)
master = place(crop_im, 1024)
master.save(os.path.join(STAGE, "ic_launcher_master.png"))
print(f"master: {os.path.join(STAGE, 'ic_launcher_master.png')}")

for dpi, size in MIPMAPS.items():
    icon = master.resize((size, size), Image.LANCZOS)
    icon.save(os.path.join(STAGE, f"ic_launcher_{dpi}.png"))

# 回读校验
print("\n=== 回读校验 ===")
for f in sorted(os.listdir(STAGE)):
    v = np.array(Image.open(os.path.join(STAGE, f)).convert("RGBA"))
    opq = (v[..., 3] > 200).sum()
    semi = ((v[..., 3] > 8) & (v[..., 3] <= 200)).sum()
    b = v[..., 3] > 8
    yy, xx = np.where(b)
    bw, bh = int(xx.max()) - int(xx.min()) + 1, int(yy.max()) - int(yy.min()) + 1
    # 检查四个角的 alpha 是否全 0（确认无卡片/阴影残留）
    corners = [v[1, 1, 3], v[-2, 1, 3], v[1, -2, 3], v[-2, -2, 3]]
    print(f"{f}: {v.shape[1]}x{v.shape[0]} 不透明px={opq} 半透明px={semi} 内容bbox={bw}x{bh} 四角alpha={corners}")
