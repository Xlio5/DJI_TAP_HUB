"""从透明 master 合成白底图标，生成各 mipmap 尺寸并写入。

白底图标 = 裁剪后的图形 合到 纯白背景(255,255,255)，四角白色不透明。
"""
from PIL import Image
import numpy as np
import os

STAGE = "c:/my_project/TUN_NAT_HUB/output/logo_icon"
RES = "c:/my_project/TUN_NAT_HUB/android/app/src/main/res"
SIZES = {"mdpi": 48, "hdpi": 72, "xhdpi": 96, "xxhdpi": 144, "xxxhdpi": 192}

master = Image.open(os.path.join(STAGE, "ic_launcher_master.png")).convert("RGBA")
assert master.size == (1024, 1024), f"master 尺寸异常: {master.size}"

# 白底合成
white = Image.new("RGBA", (1024, 1024), (255, 255, 255, 255))
white_master = Image.alpha_composite(white, master)
white_master.save(os.path.join(STAGE, "ic_launcher_white_master.png"))
print("white master saved (1024x1024)")

# 写入各尺寸
for dpi, size in SIZES.items():
    icon = white_master.resize((size, size), Image.LANCZOS)
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
    # 四角应为白色不透明
    white_corners = all(int(v[0, 0, 0]) > 250 and int(v[0, -1, 0]) > 250 for _ in [0])
    # 中心图形应保留深色
    center = v[size // 2, size // 2][:3].tolist()
    # 与 white_master 下采样比对
    ref = white_master.resize((size, size), Image.LANCZOS)
    diff = np.abs(np.array(ref).astype(int) - v.astype(int)).sum()
    print(f"{dpi:6s}: 尺寸{dims_ok} 四角alpha={corners} 中心色={center} 与white_master一致(diff={diff})")
    if not (dims_ok and all(c == 255 for c in corners) and diff == 0):
        ok = False
print("\n结果:", "全部通过 ✅" if ok else "有异常 ❌")
