"""查 UART2/UART1 LSR 寄存器 (RX 状态) + 重启 dji_rc"""
import paramiko, time

c = paramiko.SSHClient()
c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
c.connect("192.168.144.66", 22, "root", "root", timeout=15, allow_agent=False, look_for_keys=False)

def r(cmd, wait=1.5):
    _, o, e = c.exec_command(cmd)
    time.sleep(wait)
    return (o.read() + e.read()).decode(errors="replace").strip()

# UART 基址: UART0=0x1C28000, UART1=0x1C28400, UART2=0x1C28800
# LSR @ +0x14 (offset), bit0=DR(数据就绪), bit5=THRE
print("=== 1. UART LSR 寄存器 (bit0=RX有数据) ===")
print("UART1(0x1C28414):", r("devmem 0x01C28414 32"))
print("UART2(0x1C28814):", r("devmem 0x01C28814 32"))

print("\n=== 2. 连续采样 UART2 LSR 5 次 (每 1s) ===")
for i in range(5):
    v = r("devmem 0x01C28814 32")
    # bit0=1 表示 RX FIFO 有数据
    rx_ready = (int(v, 16) & 1) == 1
    print(f"[{i}] LSR=0x{v.strip()} RX数据={'有' if rx_ready else '无'}")
    time.sleep(1)

print("\n=== 3. 重启 dji_rc (固化版) ===")
print(r("/usr/local/bin/dji_rc --interval 20 --out-dev /dev/ttyS0 --out-baud auto --crsf-telem 1 --rcmsg-host 10.0.0.2 --rcmsg-port 65530 > /var/log/dji_rc.log 2>&1 & echo PID=$!"))

print("\n=== 4. 等 8 秒, rx1/rx2 ===")
time.sleep(8)
print(r("grep 'CH1=' /var/log/dji_rc.log | tail -1 | grep -oE 'rx1=[0-9]* rx2=[0-9]*'"))
c.close()
print("\n[done]")
