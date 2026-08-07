"""触发设备重启以切换到 B 槽 (OTA)"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)
print("SSH 连接: OK")

_, o, e = c.exec_command("sync; reboot")
print("重启命令已发送")
time.sleep(2)
c.close()
print("[done]")
