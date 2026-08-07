"""分析 V3s 串口分配: 物理 UART0/1/2 对应哪个 /dev/ttyS*, 以及当前占用"""
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

print("=== 1. kernel cmdline (console 配置) ===")
print(r("cat /proc/cmdline"))

print("\n=== 2. dmesg 串口注册 (UART 对应 ttyS) ===")
print(r("dmesg | grep -E 'serial|ttyS' | head -10"))

print("\n=== 3. /dev/ttyS* 设备 ===")
print(r("ls -la /dev/ttyS* 2>/dev/null"))

print("\n=== 4. 当前谁在占用串口 ===")
print(r("fuser /dev/ttyS0 /dev/ttyS1 /dev/ttyS2 2>&1; echo '---'"))
print(r("ls -la /proc/$(pidof dji_rc)/fd/ 2>/dev/null | grep -E 'ttyS'"))
print(r("ls -la /proc/$(pidof web_server)/fd/ 2>/dev/null | grep -E 'ttyS' || echo 'web_server 无串口'"))

print("\n=== 5. /dev/console 指向 ===")
print(r("ls -la /dev/console 2>/dev/null; readlink /dev/console 2>/dev/null"))

print("\n=== 6. 是否有其他程序用 ttyS0 ===")
print(r("ps w | grep -iE 'getty|ttyS0|console' | grep -v grep || echo '无 getty'"))

c.close()
print("\n[done]")
