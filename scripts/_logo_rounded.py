"""从白底 master 生成圆角图标，各尺寸写入 staging 并写回 mipmap。

圆角遮罩：rounded_rectangle，radius = 20% 边长（Android 常见圆角比例）。
"""
from PIL import Image, ImageDraw
import numpy as np
import os

STAGE = "c:/my_project/TUN_NAT_HUB/output/logo_icon"
RES = "c:/my_project/TUN_NAT_HUB/android/app/src/main/res"
SIZES = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}
RADIUS_FRAC = 0.20

def rounded(src, size):
    """src(尺寸任意) 缩放到 size，应用圆角遮罩，返回 RGBA"""
    im = src.resize((size, size), Image.LANCZOS).convert("RGBA")
    radius = int(size * RADIUS_FRAC)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    # 合并原 alpha 与圆角遮罩
    a = im.getchannel("A").point(lambda v: v * 255 // 255)  # 保持原 alpha
    im.putalpha(Image.composite(a, Image.new("L", (size, size), 0), mask))
    return im

white_master = Image.open(os.path.join(STAGE, "ic_launcher_white_master.png")).convert("RGBA")
assert white_master.size == (1024, 1024)

# master 圆角
master_rounded = rounded(white_master, 1024)
master_rounded.save(os.path.join(STAGE, "ic_launcher_rounded_master.png"))
print("rounded master saved (1024x1024)")

# 各尺寸 staging + 写 mipmap
for dpi, size in SIZES.items():
    icon = rounded(white_master, size)
    icon.save(os.path.join(STAGE, f"ic_launcher_rounded_{dpi}.png"))
    out_path = os.path.join(RES, f"mipmap-{dpi}", "ic_launcher.png")
    icon.save(out_path)
    print(f"写入 mipmap-{dpi}/{size}px")

# 回读校验
print("\n=== 回读校验 ===")
ok = True
for dpi, size in SIZES.items():
    p = os.path.join(RES, f"mipmap-{dpi}", "ic_launcher.png")
    v = np.array(Image.open(p).convert("RGBA"))
    dims_ok = v.shape[:2] == (size, size)
    corners = [int(v[0, 0, 3]), int(v[0, -1, 3]), int(v[-1, 0, 3]), int(v[-1, -1, 3])]
    # 中心应为白色不透明（图形外围）
    center_white = int(v[size // 2, size // 2, 3]) == 255
    # 与 staging 一致
    ref = np.array(Image.open(os.path.join(STAGE, f"ic_launcher_rounded_{dpi}.png")).convert("RGBA")).astype(int)
    diff = np.abs(ref - v.astype(int)).sum()
    # 圆角半径验证：中心边上 (radius 处) 应是透明
    r = int(size * RADIUS_FRAC)
    # 检查圆角顶点内一像素（左上角对角线方向）
    inside_corner = int(v[r - 1, r - 1, 3])
    print(f"{dpi:6s}: 尺寸{dims_ok} 四角alpha={corners} 中心白={center_white} 与staging一致(diff={diff}) 圆角内点alpha={inside_corner}")
    if not (dims_ok and all(c == 0 for c in corners) and center_white and diff == 0):
        ok = False
print("\n结果:", "全部通过 ✅" if ok else "有异常 ❌")
