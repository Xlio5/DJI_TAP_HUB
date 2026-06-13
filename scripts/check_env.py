"""Check RK3588 environment for web panel deployment."""
import paramiko
c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("172.24.91.28", username="xlong", password="1234", timeout=10)

def run(cmd):
    stdin, stdout, stderr = c.exec_command(cmd, timeout=15)
    out = stdout.read().decode(errors="replace")
    if out.strip():
        print(out.strip())

run("python3 --version 2>&1")
run("pip3 list 2>/dev/null | grep -iE 'flask|jinja' || echo 'Flask NOT installed'")
run("which pip3")
print("---")
run("pip3 install flask 2>&1 | tail -5")
print("---")
run('python3 -c "import flask; print(flask.__version__)" 2>&1')
print("---")
run("df -h /home/xlong | tail -1")
run("free -h | head -2")
c.close()
