"""分析 V3s U-Boot console + 内核 console 配置, 评估 UART0 释放的影响"""
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

print("=== 1. 内核 cmdline (console 配置) ===")
print(r("cat /proc/cmdline"))

print("\n=== 2. /dev/console 指向 ===")
print(r("ls -la /dev/console 2>/dev/null; cat /proc/consoles 2>/dev/null"))

print("\n=== 3. 内核串口注册 ===")
print(r("dmesg | grep -E 'ttyS|console' | head -10"))

print("\n=== 4. U-Boot 环境变量 (如果可读) ===")
print(r("ls /dev/mtd* 2>/dev/null; cat /proc/cmdline | grep -o 'console=[^ ]*'"))

print("\n=== 5. getty / 登录串口 ===")
print(r("ps w | grep -iE 'getty|login' | grep -v grep || echo '无 getty'"))

c.close()
print("\n[done]")
