"""v3：空间裁剪掉卡片装饰带(顶部淡点/左右虚线/底部投影)，再抠白只留图形本体。

装饰带坐标（基于放大渲染确认）：
- 顶部淡点：y 44-60  → 裁剪 y < 115
- 左侧虚线：x ~55    → 裁剪 x < 150
- 右侧虚线：x ~1201  → 裁剪 x > 1110
- 底部投影：y 1056+  → 裁剪 y > 1048
图形本体范围：x[190,880] y[170,1046]
"""
from PIL import Image
import numpy as np
import os

SRC = "c:/my_project/TUN_NAT_HUB/logo.png"
STAGE = "c:/my_project/TUN_NAT_HUB/output/logo_icon"
MIPMAPS = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}

# 空间裁剪带
CROP_LEFT, CROP_RIGHT = 150, 1110   # 保留 x[CROP_LEFT, CROP_RIGHT)
CROP_TOP, CROP_BOTTOM = 115, 1048   # 保留 y[CROP_TOP, CROP_BOTTOM)

im = Image.open(SRC).convert("RGBA")
a = np.array(im).astype(np.float32)
H, W = a.shape[:2]

# 1. 空间裁剪：把装饰带整体置为透明
alpha0 = np.ones((H, W), np.float32) * 255.0
alpha0[0:CROP_TOP, :] = 0
alpha0[CROP_BOTTOM:, :] = 0
alpha0[:, 0:CROP_LEFT] = 0
alpha0[:, CROP_RIGHT:] = 0

# 2. 内部白色抠成透明（软边缘）
dist = (255 - a[..., 0]) + (255 - a[..., 1]) + (255 - a[..., 2])
T_LOW, T_HIGH = 8.0, 30.0
alpha_white = np.clip((dist - T_LOW) / (T_HIGH - T_LOW), 0, 1) * 255
alpha = np.minimum(alpha0, alpha_white)  # 两者都透明才透明
rgba = np.dstack([a[..., :3], alpha]).astype(np.uint8)

# 3. 裁剪到图形包围盒（alpha>40 定边界，避免淡残留撑大bbox）
mask = alpha > 40
ys, xs = np.where(mask)
x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
gw, gh = x1 - x0 + 1, y1 - y0 + 1
print(f"图形包围盒(alpha>40): x[{x0},{x1}] y[{y0},{y1}]  宽{gw} 高{gh}  宽高比{gw/gh:.3f}")

# 检查 bbox 是否落在安全区域内（未被装饰带污染）
assert x0 >= CROP_LEFT and x1 < CROP_RIGHT and y0 >= CROP_TOP and y1 < CROP_BOTTOM, "bbox 超出安全区域!"

crop_im = Image.fromarray(rgba[y0:y1 + 1, x0:x1 + 1])

# 4. 居中放透明方形画布（图形占边长 fill 比例）
margin = 0.13
fill = 1 - 2 * margin

def place(art, size):
    c = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    aw = max(1, int(size * fill * gw / max(gw, gh)))
    ah = max(1, int(size * fill * gh / max(gw, gh)))
    art_resized = art.resize((aw, ah), Image.LANCZOS)
    c.paste(art_resized, ((size - aw) // 2, (size - ah) // 2), art_resized)
    return c

os.makedirs(STAGE, exist_ok=True)
master = place(crop_im, 1024)
master_path = os.path.join(STAGE, "ic_launcher_master.png")
master.save(master_path)
print(f"master: {master_path}")

for dpi, size in MIPMAPS.items():
    icon = master.resize((size, size), Image.LANCZOS)
    icon.save(os.path.join(STAGE, f"ic_launcher_{dpi}.png"))

# 5. 回读校验
print("\n=== 回读校验 ===")
for f in sorted(os.listdir(STAGE)):
    v = np.array(Image.open(os.path.join(STAGE, f)).convert("RGBA"))
    opq = (v[..., 3] > 200).sum()
    semi = ((v[..., 3] > 8) & (v[..., 3] <= 200)).sum()
    b = v[..., 3] > 8
    yy, xx = np.where(b)
    bw, bh = int(xx.max()) - int(xx.min()) + 1, int(yy.max()) - int(yy.min()) + 1
    corners = [int(v[1, 1, 3]), int(v[-2, 1, 3]), int(v[1, -2, 3]), int(v[-2, -2, 3])]
    print(f"{f}: {v.shape[1]}x{v.shape[0]} 不透明px={opq} 半透明px={semi} 内容bbox={bw}x{bh} 四角alpha={corners}")
