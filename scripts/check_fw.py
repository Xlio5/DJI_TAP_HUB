import paramiko, time

for i in range(8):
    try:
        ssh = paramiko.SSHClient()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect("192.168.144.66", username="root", password="root", timeout=3, banner_timeout=3)
        _, o, _ = ssh.exec_command("wget -q -O - http://127.0.0.1:8080/ 2>&1 | grep -c firmware", timeout=5)
        count = o.read().decode().strip()
        print("Firmware page: " + ("FOUND" if count == "1" else "MISSING"))
        _, o, _ = ssh.exec_command("ps | grep -c web_server", timeout=3)
        print("web_server running: " + o.read().decode().strip())
        ssh.close()
        break
    except Exception as e:
        print("Attempt " + str(i+1) + ": " + str(e)[:60])
        time.sleep(5)
