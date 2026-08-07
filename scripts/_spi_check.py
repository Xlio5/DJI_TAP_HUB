"""检查 V3s SPI 资源: SPI 是否被占用, 能否给串口转 SPI 芯片用"""
import paramiko, time

def ssh_connect(host, user, pw, retries=6, timeout=12):
    for i in range(retries):
        try:
            c = paramiko.SSHClient()
            c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            c.connect(host, 22, user, pw, timeout=timeout, allow_agent=False,
                      look_for_keys=False, banner_timeout=timeout, auth_timeout=timeout)
            return c
        except Exception as e:
            print(f"  [重试{i+1}] {e}")
            time.sleep(3)
    return None

c = ssh_connect("192.168.144.66", "root", "root")
if not c:
    print("V3s SSH 失败"); exit(1)

def r(cmd, wait=0.5):
    _, out, err = c.exec_command(cmd)
    time.sleep(wait)
    return (out.read() + err.read()).decode(errors="replace").strip()

print("=== 1. SPI 设备树 / 驱动 ===")
print(r("ls /dev/spidev* 2>/dev/null || echo '无 spidev'"))
print(r("dmesg | grep -iE 'spi|sunxi-spi' | head -10"))

print("\n=== 2. SPI flash (启动用的) 占用哪个 SPI ===")
print(r("cat /proc/mtd 2>/dev/null"))
print(r("ls -la /sys/bus/spi/devices/ 2>/dev/null"))

print("\n=== 3. GPIO 资源 (SPI 引脚有没有空闲) ===")
print(r("cat /sys/kernel/debug/gpio 2>/dev/null | head -20 || echo '无 gpio debug'"))

print("\n=== 4. sunxi SPI 控制器 ===")
print(r("dmesg | grep -iE 'spi[0-9]|spi-master|sun6i' | head -10"))

c.close()
print("\n[done]")
