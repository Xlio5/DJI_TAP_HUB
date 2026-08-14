# CRSF-Lua 真机调试交接文档（可复制到新会话）

> 生成时间: 2026-08-14
> 会话主题: DJI RC / V3s / ELRS 的 CRSF-Lua 桥接（安卓 App 跑 elrsV3.lua 配置 ELRS 参数）
> 用途: 新会话直接复制本文件全部内容作为上下文, 无需重跑前期调试

---

## 一、最终目标

**DJI RC 遥控器 → V3s 中转 → SBUS/CRSF 输出，配套 Android App 配置 + 双向回传。**

当前正在做的具体目标：
**让安卓 App 跑 elrsV3.lua 脚本，经 V3s bridge 连 ELRS 高频头，实现 ELRS 参数配置界面（上下选择 + 改值 + 编辑高亮）。**

完整链路：
```
安卓App(跑 elrs.lua) → VPN(tun0 10.0.0.2) → USB隧道 → V3s bridge(UDP 65532)
    → UART0(115200) → 电脑桥 → ELRS 高频头
    → ELRS 响应(Device_Info/Settings_Entry) → 桥 → V3s UART0 → crsf_rx_thread → UDP → App → Lua 渲染
```

**✅ 2026-08-14 已打通**：App 在 DJI RC 真机上渲染出 ELRS 真实参数界面（Packet Rate/Telem Ratio/Switch Mode）。

---

## 二、关键背景（硬件/网络/环境）

### 设备
| 设备 | 说明 | 连接 |
|---|---|---|
| **DJI RC PLUS 2** (rc701) | 遥控器, adb 连接 | 双 USB 口: 一个连电脑(adb), 一个连 V3s(隧道 host) |
| **V3s** | Allwinner V3s, Buildroot 2024.02 | LAN 192.168.144.66 + 172.20.10.3（双 IP） |
| **ELRS 高频头** | T-14 900 TX, Silicon Labs CP210x | 电脑 **COM37**，波特率 **115200** |
| **V3s UART0** (ttyS0) | USB-SERIAL CH340 | 电脑 **COM5**，波特率 115200（ELRS Lua） |

### 参考实现（关键！）
**`c:/my_project/elrs_lua_python/`** —— Python 完整 ELRS Lua 实现（另一台机器，本机无）。本次调试自行实现验证。

### 分支
- 当前分支：`feature/crsf-lua-m4`
- 远程：Gitee `origin`

---

## 三、已确认的事实（经过验证）

### 波特率（重要！）
- **ELRS Lua backchannel 用 115200**（V3s UART 24M 时钟分频, 400000 非整数导致实际输出偏离, ELRS 锁不到）
- **V3s UART0 = 115200**（S99 参数 + SPI flash 配置均为此）
- ELRS autobaud 列表: {400000, 115200, 5250000, 3750000, 1870000, 921600, 2250000}

### CRSF 协议（关键！）
- 帧格式: `[addr][len][type][dest][orig][payload][crc]`
- **CRC8 poly 0xD5，从 type 起计算（ELRS/EdgeTX 标准）**——不是从 addr 起！
- 地址: `0xEE`=ELRS TX 模块, `0xEA`=遥控器, `0x00`=广播
- 帧类型: 0x28 Device_Ping, 0x29 Device_Info, 0x2B Settings_Entry, 0x2C Parameter_Read, 0x2D Parameter_Write, 0x3A ELRS_STATUS
- **Device_Ping 广播**: `ee 04 28 00 ea 54`（crc 从 type 起）
- Parameter_Read: `ee 06 2c ee ea <param> <chunk> <crc>`（crc 从 type 起 5 字节）

### ELRS 交互流程（已验证）
- **ping 节奏 ~1s**（150ms 太快 ELRS 不响应）
- ping → Device_Info(0x29) → 识别设备（App title 显示 "T-14 900 TX"）
- Parameter_Read(0x2C, param, chunk) → Settings_Entry(0x2B) → 参数
- **chunk 流式返回**（ELRS 按内部顺序返回块, 续读 chunk 递增到 remain=0）
- Parameter_Write(0x2D) → 写参数（读回确认生效）

### V3s 关键事实
- **crsf_rx_byte 的 CRC 校验必须从 type 起**（修复前从 addr 起, ELRS 帧全被拒）
- **bridge fwd 写入 UART0 需重试**（摇杆帧占 TX 时 O_NONBLOCK write EAGAIN 丢参数帧）
- V3s eth0 (192.168.144.66) UDP 本地投递坏；App 走 tun_hub (10.0.0.1)
- UDP↔UART 双向透传已验证（阻塞 read/recvfrom）

### App 关键事实
- **发包必须 bindProcessToVpnNetwork()**（否则 Android 默认走 wlan0 到不了 V3s）
- **收包用 openProtectedPort(65532)**（内核才投递 TUN 入站 UDP）
- **buildCrsfFrame CRC 范围 len→len+1**（否则 Parameter_Read crc 错, ELRS 拒绝）
- CrsfBridge host = 10.0.0.1（tun_hub, 不是 eth0）

---

## 四、长期偏好

1. **称呼用户为"老大"**（每次回复必须出现）
2. **自动化**：所有操作（构建/部署/测试/git）AI 直接执行，不让用户手动敲指令
3. **中文交流**，技术术语保留英文
4. **知识回流**：解决非显而易见的 bug/决策 → 写入 Obsidian Vault
5. 写文档/记录到项目 docs/ 下，方便跨会话

---

## 五、硬性规则（CLAUDE.md，最高优先级）

1. **称呼老大**：所有回复必须含"老大"
2. **失败 2 次停手**：连续失败 2 次禁止试第 3 次
3. **硬件操作一次性列全**
4. **被指出"不要逃避"时**：立刻停手复盘回根因
5. **写后必须读回验证**
6. **每次编译变更必须同步递增版本号**：固件 web_server.cpp VERSION, App build.gradle.kts versionCode/versionName

---

## 六、输出格式

- Git commit：`<type>(<scope>): 描述`
- 中文注释
- 回复用清晰分节（## 或表格）

---

## 七、当前进度（2026-08-14，已打通）

### ✅ 完整链路已通
```
App(接收机页, elrsV3.lua) → VPN(tun0) → USB → V3s bridge → UART0(115200)
→ 桥(COM5↔COM37) → ELRS
→ Device_Info(0x29)/Settings_Entry(0x2B) → 桥 → V3s → crsf_rx_thread(CRC修复) → UDP → App
→ LuaEngine → elrsV3.lua 渲染参数界面 ✅
```

**验证结果**：
- App 识别设备 title = "T-14 900 TX"
- 渲染参数: Packet Rate=100Hz(-117dBm), Telem Ratio=1:8, Switch Mode=Hybrid 等（6 行/页）
- Parameter_Read/Write 到 ELRS 正常

### 修复清单（7 个根因，2026-08-15 补充）
| # | 修复 | 文件 |
|---|---|---|
| 1 | crsf_rx_byte CRC 校验起点 addr→type | ubuntu/src/crsf.c |
| 2 | bridge fwd 写入重试（摇杆占 TX） | ubuntu/src/dji_rc.cpp |
| 3 | CrsfBridge 收发分离 + bind 65532 + openProtectedPort | CrsfBridge.kt |
| 4 | bindProcessToVpnNetwork（发包走 tun0） | CrsfBridge.kt |
| 5 | buildCrsfFrame CRC 范围 len→len+1 | LuaEngine.kt |
| 6 | **dji_rc crsf_rx_thread 启动条件 + 跳过摇杆输出**（bridge 模式上行转发 + 不干扰 ELRS backchannel）| dji_rc.cpp |
| 7 | **App 发包走 tun0 路由修复**：bindSocketToVpn + UDP connect（bindProcessToNetwork 不彻底，uid 规则覆盖）| CrsfBridge.kt + TunNatVpnService.kt |

### UI 改进（App 1.6.11+）
- 右侧操作按钮列（▲▼确认返回）
- 选中行 ▶ 箭头 + selectedLine 跟踪
- 编辑模式 BLINK 闪烁提醒

### ✅ 已解决（2026-08-15）
1. ~~Device_Info 偶发丢~~ → 根因: crsf_rx_thread 未启动 + 摇杆干扰, 已修复
2. ~~参数渲染偶发 0 行~~ → 随 #1 解决
3. ~~App 发包走 wlan0~~ → bindSocketToVpn + connect 修复
4. **400k 波特率**：V3s DLF 精确输出 401070(+0.27%), ELRS 兼容（见 docs/CRSF_400K_BAUD_NOTES.md）

### ⚠️ 遗留
1. **电脑桥中转 400k 乱码**：电脑桥 @400000 读 V3s 401070 偏差 0.27% 乱码；V3s 直连 ELRS 时 400k 正常（需改接线验证）
2. **固件已固化 v1.6.12**（400k 默认），但 115200 验证通过（当前跑 115200）

---

## 八、调试方式方法（本次沉淀）

### 8.1 硬件拓扑
```
DJI RC(双USB口) ─┬─ USB1 → 电脑(adb 部署/日志)
                 └─ USB2 → V3s(USB隧道, host 模式)
V3s UART0 → 电脑 COM5 (115200)
ELRS 高频头 → 电脑 COM37 (115200)
电脑桥: COM5 ↔ COM37 透明转发 + 帧监测
```

### 8.2 关键工具（tmp/）
| 工具 | 用途 |
|---|---|
| `_com_bridge.py` | 电脑桥 COM5↔COM37（参数化, 打印双向帧） |
| `_udp_send.c` | V3s 发 Device_Ping 到指定 IP:port |
| `_baud_scan.py` | 扫描 V3s 实际波特率 |
| `_crsf_parse2.py` / `_parse_frames.py` | 解析桥日志 CRSF 帧 |
| `_elrs_param_read*.py` | ELRS Lua 参数读取（分块续读） |
| `_elrs_param_write.py` | Parameter_Write 测试 |
| `_elrs_chunk_verify.py` | chunk 分块协议验证 |
| `_deploy_dbg.py` | 部署调试版 dji_rc 到 V3s |
| `_v3s_status.py` | SSH 查 V3s 状态 |
| `_build_v169.sh` | 固件交叉编译 |

### 8.3 调试流程
1. **桥监测**：`python tmp/_com_bridge.py --a COM5 --b COM37 --baud 115200 > tmp/bridge.log`（看双向帧）
2. **帧对比**：从桥日志提取帧，和电脑直连对比（如 Parameter_Read crc）
3. **V3s 状态**：`python tmp/_v3s_status.py`（进程/日志/波特率）
4. **部署调试版**：`python tmp/_deploy_dbg.py`（stdin 管道传输 + md5 校验 + 重启）
5. **App 日志**：`adb logcat | grep CrsfBridge|LuaParam|LuaEngine`
6. **UDP 统计**：`cat /proc/net/snmp | grep Udp`（InDatagrams/NoPorts 判断包到达）
7. **/proc/net/udp**：确认 socket 监听
8. **/proc/net/dev**：tun_hub/tun0 rx/tx 判断隧道方向

### 8.4 常用排查命令
```bash
# V3s bridge recv/fwd 计数
grep -c 'bridge recv' /var/log/dji_rc.log
grep -c 'bridge fwd' /var/log/dji_rc.log

# V3s crsf_rx_thread 转发日志
grep 'crsf_rx.*frame' /var/log/dji_rc.log

# App 收包 socket
adb shell "netstat -an | grep 65532"

# App 发包走 tun0
adb shell "cat /proc/net/dev | grep tun0"

# 桥日志帧长度分布（找 ping 6B/Parameter_Read 8B/Settings_Entry）
PYTHONIOENCODING=utf-8 python -c "
import re, collections
text = open(r'tmp/bridge.log', encoding='latin-1', errors='ignore').read()
print(dict(collections.Counter(int(x) for x in re.findall(r'\] (\d+)B:', text)).most_common(5)))
"
```

---

## 九、尚未完成的任务（按优先级）

1. **Device_Info(36B) 偶发丢**：App 识别不稳定 → 排查 V3s crsf_rx 转发 vs App 收包 socket
2. **参数渲染偶发 0 行**：识别后 Settings_Entry 持续交互
3. **固件固化**：把验证过的 dji_rc 固化到固件（含 crsf_rx CRC 修复 + fwd 重试），版本递增
4. **清理调试工具**：tmp/ 一次性诊断脚本
5. **版本号同步 + 文档**

---

## 十、不能随意修改的内容

1. **CLAUDE.md 强制规则**
2. **crsf.c 的 crsf_rx_byte CRC 从 type 起**（ELRS 帧解析, 勿改回 addr 起）
3. **App bindProcessToVpnNetwork + openProtectedPort**（隧道收发关键）
4. **App buildCrsfFrame CRC len+1**（Parameter_Read crc 正确）
5. **波特率 115200**（V3s UART 分频精确）
6. **S99/setup_v3s.sh LF 换行 + 双 IP**
7. **固件构建用 base rootfs 提取**

---

## 十一、新会话接下来先做什么

1. **稳定 App 识别**：排查 Device_Info(36B) 偶发丢（V3s crsf_rx 转发 vs App 收包）
2. **确认 UI 高亮**：参数渲染后按确认验证 BLINK 闪烁
3. **固件固化**：把验证过的 dji_rc 固化（crc + fwd 重试），重新打包 rootfs + 版本递增
4. 更新 PRD 里程碑（CRSF-Lua M4 真机验证）
