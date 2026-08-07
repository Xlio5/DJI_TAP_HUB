"""盘点当前 V3s 板的调试/访问通道"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

print("=== 1. 网络接口 ===")
print(r("ip addr show 2>/dev/null | grep -E '^[0-9]+:|inet ' || ifconfig 2>/dev/null | grep -E '^[a-z]|inet '"))
print("\n=== 2. USB 设备 (OTG/device 模式?) ===")
print(r("ls /sys/bus/usb/devices/ 2>/dev/null | head; echo '---'; cat /proc/cmdline | grep -oE 'g_serial[^ ]*'"))
print("\n=== 3. USB gadget 配置 ===")
print(r("ls /sys/kernel/config/usb_gadget/ 2>/dev/null || echo '无 usb_gadget'; ls /sys/class/udc/ 2>/dev/null || echo '无 udc'"))
print("\n=== 4. 当前运行服务 ===")
print(r("ps w | grep -E 'web_server|dji_rc|usb_tund|dropbear|sshd' | grep -v grep"))
print("\n=== 5. 串口 (ttyS0-2) 用途 ===")
print(r("ls -la /dev/ttyS* 2>/dev/null"))
print("\n=== 6. 网络配置 (eth0 IP) ===")
print(r("cat /etc/network/interfaces 2>/dev/null | grep -E 'iface|address'; ip addr show eth0 2>/dev/null | grep inet"))
c.close()
print("\n[done]")
