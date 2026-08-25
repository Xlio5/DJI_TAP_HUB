# 2026-08-25 RTSP 视频与固件固化计划

## 目标

固化 V3s 固件中的 TUN/NAT/RTSP 回流配置，让重启和重新刷机后仍保持当前调试结论：

- UART0 作为 debug 控制台保留在 bootargs 中。
- V3s `tun_hub` 固定为 `10.0.0.1/24`。
- Android 手机主隧道地址为 `10.0.0.2`。
- 手机 LAN 身份 `x.x.x.11` 经 V3s DNAT 到 `10.0.0.2`。
- 手机主动访问 LAN 摄像头时，V3s 对 `x.x.x.11/32 -> eth0` 做 MASQUERADE，避免摄像头回包绕过 V3s。
- RTSP UDP RTP 回流目标固定为 Android 主隧道地址 `10.0.0.2`。

## 已确认异常原因

1. **固件构建路径和现场脚本不一致**
   - 现场调通的是 `ubuntu/scripts/setup_v3s.sh`。
   - `scripts/build_rootfs_only_current.sh` 之前仍拷贝 `setup_v3s_fixed.sh` 到 rootfs 的 `/usr/local/bin/setup_v3s.sh`。
   - `setup_v3s_fixed.sh` 内容落后，缺少 LAN 身份 DNAT/SNAT 逻辑。
   - 结果是现场临时修复有效，但重新打包 rootfs 后会刷回旧 NAT 逻辑。

2. **RTSP UDP 回流目标曾指向错误地址**
   - V3s `web_server` 旧逻辑把摄像头 RTP UDP DNAT 到 `192.168.144.11`。
   - 当前 Android/VPN 投递路径更稳定的目标是主隧道地址 `10.0.0.2`。
   - 已在上一提交 `24385a0 fix(ubuntu): 修复 RTSP UDP DNAT 目标` 中修复。

3. **手机主动访问摄像头需要 SNAT**
   - 手机以 LAN 身份 `192.168.144.11` 主动访问 `192.168.144.31:554` 时，如果不在 V3s 出 eth0 前做 SNAT，摄像头会尝试直接 ARP `192.168.144.11`。
   - 该回包路径绕过 V3s，导致 TCP/RTSP 握手不稳定或卡住。
   - 固化规则：`POSTROUTING -s <LAN_PHONE_IP>/32 -o eth0 -j MASQUERADE`。

4. **当前最终视频验证被摄像头离线阻断**
   - V3s 侧 `ping 192.168.144.31` 无响应。
   - `arping -I eth0 192.168.144.31` 无响应。
   - `ip neigh show dev eth0` 中 `192.168.144.31 FAILED`。
   - 同网段仅观察到 `192.168.144.88`，但该地址 `554` 端口拒绝连接，不是当前 RTSP 摄像头。

## 本轮固化改动

- `ubuntu/scripts/setup_v3s.sh`
  - 固化 `10.0.0.1/24`、`10.0.0.2`、`x.x.x.11/32` 路由。
  - 固化 LAN 身份 DNAT。
  - 固化手机 LAN 身份出 eth0 的 MASQUERADE。

- `ubuntu/scripts/setup_v3s_fixed.sh`
  - 同步为与 `setup_v3s.sh` 等价的逻辑。
  - 保留文件名只兼容旧脚本，避免旧构建入口再次打出错误 rootfs。

- `scripts/build_rootfs_only_current.sh`
  - 改为直接拷贝 `ubuntu/scripts/setup_v3s.sh`。

- `ubuntu/src/web_server.cpp`
  - 固件版本递增到 `1.6.45`。

## 验证门槛

- 源码级验证
  - `sh -n ubuntu/scripts/setup_v3s.sh`
  - `sh -n ubuntu/scripts/setup_v3s_fixed.sh`
  - `bash -n scripts/build_rootfs_only_current.sh`
  - `ctest` 或等价单元测试验证 `rtsp_nat_helper`。

- 产物级验证
  - rootfs 文件名包含版本和时间戳。
  - SPI 镜像文件名包含版本和时间戳。
  - release 目录包含 manifest。
  - rootfs 解包读回确认：
    - `/usr/local/bin/setup_v3s.sh` 包含 `INTERNAL_FWD_ADDR=10.0.0.2`。
    - `/usr/local/bin/setup_v3s.sh` 包含 `MASQUERADE`。
    - `/usr/local/bin/web_server` 字符串包含 `1.6.45`。
  - SPI 镜像 `0x710000` 位置 rootfs magic 为 `hsqs`。
  - SPI 镜像切片出的 rootfs SHA256 与 release rootfs SHA256 一致。
  - SPI bootargs 包含 `console=ttyS0,115200`。

## 现场复测步骤

1. 刷入本轮 release 目录中的完整 16MiB SPI 镜像。
2. UART0/COM10 观察启动日志或 getty。
3. SSH 到 `192.168.144.66` 后检查：
   - `ip addr show tun_hub`
   - `ip route`
   - `iptables -t nat -S`
   - `wget -q -O - http://127.0.0.1:8080/api/version`
4. 摄像头恢复在线后检查：
   - `arping -I eth0 192.168.144.31`
   - `nc -zv 192.168.144.31 554`
   - App 播放 RTSP。
   - V3s 抓包确认 RTP UDP 从摄像头进入 eth0，并被 DNAT 到 `10.0.0.2`。

## 当前结论

本轮能固化的是 V3s 侧路由/NAT/版本/刷机产物；当前不能声称 App 视频最终通过，因为摄像头 `192.168.144.31` 在最后一轮验证时已经离线。
