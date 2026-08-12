# CRSF 真机调试进度 (2026-08-13 深夜)

## ✅ 固件侧
- v1.6.7 OTA: dji_rc 34a35170, bridge 监听 0.0.0.0:65532, strace 确认 recvfrom(fd9=65532) 活跃
- RC USB 连 V3s, App 连接 + tun0 + 视频通

## 🔍 决定性发现 (V3s bridge 收包 bug)
- **电脑发包到 192.168.144.66:65532 → tcpdump eth0 抓到包到达**
- **但 /proc/net/udp 65532 rx_queue=0 + strace recvfrom EAGAIN**
- → 包到 eth0 但**未投递到本地 65532 socket**
- iptables INPUT ACCEPT, 无 DNAT(源.88不匹配), rp_filter=0, 路由正确, fd9=socket[1613]=65532
- 疑似 V3s 内核 eth0 UDP 本地投递问题 (视频 UDP 转发正常, 但 INPUT 本地投递不通)

## 待验证/修复
1. V3s 本地 loopback 发包到 65532 测 socket 层 (需工具)
2. 检查 eth0 driver/INPUT 投递
3. 或 bridge 改用原始 socket (SOCK_RAW) 绕过投递

## App 侧 (已完成部分)
- CrsfBridge bind tun0 + host 改 192.168.144.66 + 移除 allowBypass (已提交)
- 但 V3s bridge 收包 bug 是当前主要阻塞
