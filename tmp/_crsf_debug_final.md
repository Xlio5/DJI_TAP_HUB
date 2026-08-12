# CRSF 真机调试最终结论 (2026-08-13)

## 确凿根因: V3s eth0 UDP 本地投递(INPUT) bug
- 电脑发包到 192.168.144.66:65532
- tcpdump eth0 抓到包到达 (6 包)
- 但 strace dji_rc recvfrom(fd9=65532) 无任何返回 + /proc/net/udp rx_queue=0
- → 包到 eth0 但未投递到本地 UDP socket (INPUT 路径)
- 视频 UDP (摄像头→V3s→RC) 走 FORWARD 正常 (135MB), 本地 INPUT UDP 不通
- iptables INPUT ACCEPT / 无 DNAT 匹配 / rp_filter=0 / 路由正确 / fd9=65532

## 已排查排除
- DNAT: 源.88 不匹配 .31 规则
- fd: fd9 = socket[1613] = 65532 ✓
- bridge 线程: recvfrom 活跃 (EAGAIN)
- 双 dji_rc: 已清 (只留 109)
- App 侧: allowBypass 移除, host 改 192.168.144.66, bind tun0

## 待老大决策
1. V3s 内核 dwmac 驱动 UDP INPUT 投递问题 (改内核/DTB)
2. bridge 改用 AF_PACKET 原始 socket 收 eth0 包 (绕过 IP 投递)
3. App 走 tun_hub INPUT (10.0.0.1), 需确认 tun_hub UDP 投递是否正常
4. 或换网卡/降级内核

## 固件侧已全部就绪
- v1.6.7: dji_rc 34a35170 (PB6 bridge 补启动), bridge 监听 0.0.0.0:65532
