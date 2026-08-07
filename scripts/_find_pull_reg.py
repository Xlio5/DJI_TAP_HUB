"""查 sun8i-v3s pinctrl 的 pull-up 寄存器偏移"""
import subprocess

# 1. 内核 pinctrl sunxi 源码 (pull-up 寄存器)
r = subprocess.run(["wsl", "bash", "-lc", "grep -rn 'PIO_PULL\\|PULL_CTL\\|pull.*0x1c\\|SUNXI_PULL\\|PULL_REG' /home/xlong/v3s/linux/drivers/pinctrl/sunxi/*.c /home/xlong/v3s/linux/drivers/pinctrl/sunxi/*.h 2>/dev/null | head -20"], capture_output=True, text=True)
print("=== pull 寄存器定义 ===")
print(r.stdout or "无")

# 2. sunxi pinctrl 的偏移计算 (pull = 0x1c? 还是别处)
r = subprocess.run(["wsl", "bash", "-lc", "grep -rn 'PIO_PULL\\|SUNXI_PINCTRL_PULL\\|pull_offset\\|0x1c' /home/xlong/v3s/linux/drivers/pinctrl/sunxi/pinctrl-sunxi.c 2>/dev/null | head -20"], capture_output=True, text=True)
print("=== pinctrl-sunxi.c pull ===")
print(r.stdout or "无")

# 3. 检查 sun8i-v3s pinctrl 数据 (bank 定义)
r = subprocess.run(["wsl", "bash", "-lc", "grep -A10 'v3s' /home/xlong/v3s/linux/drivers/pinctrl/sunxi/pinctrl-sun8i-v3s.c 2>/dev/null | head -30"], capture_output=True, text=True)
print("=== pinctrl-sun8i-v3s.c ===")
print(r.stdout or "无此文件")
