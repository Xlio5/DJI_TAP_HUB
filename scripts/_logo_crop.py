"""裁剪 logo.png 的白色圆角卡片边框，只保留深色图形本体，生成各尺寸 app 图标。

流程：
1. 近白色背景抠成透明（软边缘，避免生硬锯齿）
2. 裁剪到图形包围盒
3. 居中放到透明方形画布（带安全边距）
4. 生成 master + 各 mipmap 尺寸
"""
from PIL import Image
import numpy as np
import os

SRC = "c:/my_project/TUN_NAT_HUB/logo.png"
STAGE = "c:/my_project/TUN_NAT_HUB/output/logo_icon"
MIPMAPS = {
    "mdpi": 48,
    "hdpi": 72,
    "xhdpi": 96,
    "xxhdpi": 144,
    "xxxhdpi": 192,
}
RES_BASE = "c:/my_project/TUN_NAT_HUB/android/app/src/main/res"

im = Image.open(SRC).convert("RGBA")
a = np.array(im).astype(np.float32)

# 与白色的距离（RGB 三个通道偏差之和）
dist = (255 - a[..., 0]) + (255 - a[..., 1]) + (255 - a[..., 2])

# 软抠图：dist<=T_LOW 完全透明，dist>=T_HIGH 完全不透明，中间线性过渡
T_LOW, T_HIGH = 12.0, 42.0
alpha = np.clip((dist - T_LOW) / (T_HIGH - T_LOW), 0, 1) * 255
out = np.dstack([a[..., :3], alpha])

# 裁剪到非透明区域包围盒
mask = alpha > 8
ys, xs = np.where(mask)
x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
gw, gh = x1 - x0 + 1, y1 - y0 + 1
print(f"图形包围盒: x[{x0},{x1}] y[{y0},{y1}]  宽{gw} 高{gh}  宽高比{gw/gh:.3f}")

crop = out[y0:y1 + 1, x0:x1 + 1]
crop_im = Image.fromarray(crop.astype(np.uint8))

# 居中放到方形透明画布，margin 使图形占边长 80%
margin = 0.10
canvas = int(max(gw, gh) / (1 - 2 * margin))
print(f"画布尺寸: {canvas}x{canvas}")

def place(art, size):
    canvas_im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    art_resized = art.resize((int(size * gw / max(gw, gh)), int(size * gh / max(gw, gh))), Image.LANCZOS)
    aw, ah = art_resized.size
    canvas_im.paste(art_resized, ((size - aw) // 2, (size - ah) // 2), art_resized)
    return canvas_im

# master 1024
master = place(crop_im, 1024)
master_path = os.path.join(STAGE, "ic_launcher_master.png")
os.makedirs(STAGE, exist_ok=True)
master.save(master_path)
print(f"master: {master_path}")

# 各尺寸
for dpi, size in MIPMAPS.items():
    icon = master.resize((size, size), Image.LANCZOS)
    out_path = os.path.join(STAGE, f"ic_launcher_{dpi}.png")
    icon.save(out_path)
    print(f"{dpi}: {out_path} ({size}x{size})")

# 回读校验
print("\n=== 回读校验 ===")
for f in sorted(os.listdir(STAGE)):
    p = os.path.join(STAGE, f)
    v = np.array(Image.open(p).convert("RGBA"))
    opq = (v[..., 3] > 200).sum()
    semi = ((v[..., 3] > 8) & (v[..., 3] <= 200)).sum()
    bbox_ok = (v[..., 3] > 8)
    if bbox_ok.any():
        yy, xx = np.where(bbox_ok)
        bw, bh = int(xx.max()) - int(xx.min()) + 1, int(yy.max()) - int(yy.min()) + 1
    else:
        bw = bh = 0
    print(f"{f}: {v.shape[1]}x{v.shape[0]}  不透明px={opq} 半透明px={semi}  内容包围盒宽{bw} 高{bh} (画布{v.shape[1]}x{v.shape[0]})")
