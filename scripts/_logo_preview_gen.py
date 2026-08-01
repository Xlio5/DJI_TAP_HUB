"""生成裁剪后图标的预览图（棋盘格透明背景 + 放大），便于老大直接查看效果"""
from PIL import Image, ImageDraw

master = Image.open("c:/my_project/TUN_NAT_HUB/output/logo_icon/ic_launcher_master.png").convert("RGBA")

# 放大到 512 便于查看（图本身 1024，直接展示太大，取 512）
preview = master.resize((512, 512), Image.LANCZOS)

# 生成棋盘格透明背景
CELL = 32
checker = Image.new("RGBA", (512, 512), (255, 255, 255, 255))
d = ImageDraw.Draw(checker)
for y in range(0, 512, CELL):
    for x in range(0, 512, CELL):
        if (x // CELL + y // CELL) % 2 == 0:
            d.rectangle([x, y, x + CELL - 1, y + CELL - 1], fill=(200, 200, 200, 255))

# 合成：棋盘格在下，图形在上
combined = Image.alpha_composite(checker, preview)

out = "c:/my_project/TUN_NAT_HUB/output/logo_icon/preview_checkerboard.png"
combined.save(out)
print("saved:", out)

# 同时保存一张纯白背景 + 一张纯深色背景，模拟浅色/深色桌面
for bg, name in [((255, 255, 255), "preview_white"), ((30, 30, 30), "preview_dark")]:
    solid = Image.new("RGBA", (512, 512), bg + (255,))
    comb = Image.alpha_composite(solid, preview)
    comb.save(f"c:/my_project/TUN_NAT_HUB/output/logo_icon/{name}.png")
    print("saved:", f"c:/my_project/TUN_NAT_HUB/output/logo_icon/{name}.png")
