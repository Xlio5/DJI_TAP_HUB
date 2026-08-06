# TUN_NAT_HUB 项目交接文档

> 生成日期: 2026-08-05
> 用途: 复制到新会话继续工作

---

## 一、最终目标

DJI RC 遥控器 → V3s 中转 → SBUS/CRSF 输出，配套 Android App 配置。

1. **V3s 输出标准 SBUS/CRSF 协议**（UART0，可变波特率）
2. **App 可配置**：SBUS/CRSF 切换、通道映射（EdgeTX 风格）、波特率
3. **PB6 检测切换 UART0 角色**：上拉=协议输出，接地=debug 串口（含运行中自动切换）
4. **CRSF 双向回传**（遥控数据 + 遥测数据）

## 二、关键背景

- V3s 只有 3 个 UART：UART0(ttyS0)/UART1(ttyS1)/UART2(ttyS2)
- UART0 原本是内核 console + debug 串口，现释放为协议输出
- 硬件已定：**PB6 默认上拉**，接地触发 debug 模式
- V3s 内存仅 50MB，rootfs 是只读 squashfs（4.468MB 分区）
- 系统：BusyBox（无 pkill，用 killall）、3.4 内核 7.1.0
- 交叉编译：WSL Ubuntu-20.04 + arm-linux-gnueabihf-g++（GCC 10.5）

## 三、已确认的事实（证据）

### 物理电平
```
devmem 0x01C20834 (PB DATA):
  上拉 → 0x00000040 (bit6=1)
  接地 → 0x00000000 (bit6=0)
```
PB6 物理电平变化正常。

### 寄存器布局（sun8i-v3s pinctrl @0x01C20800）
```
BANK_MEM_SIZE = 0x24, PULL_REGS_OFFSET = 0x1c
PB = bank 1 → bank offset 0x24
  CFG0 (PB0-3) @0x24, CFG1 (PB4-7) @0x28, PB6 = CFG1 bit24-25 (0=input)
  DATA @0x34, PB6 = bit6
  PU0  @0x40, PB6 = bit12-13 (01=pull-up)
```
**关键坑**：0x01C20800 & ~0xFFF = 0x01C20000 是 clock 区！mmap 必须加页内偏移 **0x800** 才到 pinctrl。

### 串口输入正常
- ttyS1 (921600) / ttyS2 (115200) 有 DUML 数据流入（0x55 起始）
- dji_rc 解码正常（g1/g2 增长）

### SBUS 输出正常（当前）
- 上拉 → UART0 输出 SBUS 100k 8E2，`out ok mode=s`
- 有输入时才发（无输入则无输出，正常）

## 四、长期偏好

1. **称呼用户为"老大"**（CLAUDE.md 硬性规则）
2. 所有注释用中文
3. 每完成一轮改动立即 git commit
4. 知识回流到 Obsidian Vault
5. 失败 2 次必须停手诊断，报告根因，等确认

## 五、硬性规则（CLAUDE.md）

1. 回复必须含"老大"
2. 失败即停手，连续 2 次失败禁止第 3 次，先诊断
3. 硬件操作一次性完成
4. 被指"不要逃避"时立刻复盘回根因
5. 写后必须读回验证
6. 失败 2 次后提出完整分析报告
7. 所有操作 AI 直接执行，不让用户手动敲指令
8. 遇到问题先分析再动手，禁止看到报错就盲目改

## 六、输出格式

- 固件版本 v1.4.6，App 版本 v1.3.0
- 代码引用用 markdown 链接 `[文件](路径:行号)`
- 汇报用表格清晰呈现验证结果

## 七、已经完成的工作

### SBUS/CRSF 功能（完整）
- crsf.h/c：CRSF 编解码器（CRC-8 poly 0xD5，22 通道×11bit，回传解析）
- rc_map.h/c：EdgeTX 风格通道映射（16 通道×source，AETR/TAER/custom）
- dji_rc：SBUS/CRSF 输出、CRSF 回传线程、UDP 65531 TLM
- web_server：/api/rc/output 配置 + /api/rc/telemetry 回传
- App v1.3.0：RC 输出配置界面 + SBUS 标准开关 + 配置读取修复
- SBUS 标准选项：默认 100k 8E2，可切 115200 8N1

### PB6 检测 + 运行中自动切换（完整，已修复验证）
- dji_rc pb6_grounded()：mmap /dev/mem 读寄存器，**每次检测重新 open+mmap+munmap**（页内偏移 0x800）
- 运行中自动切换：每 2s poll，连续 3 次防抖，接地↔上拉实时切换
- U-Boot bootcmd：PB6 检测（接地→console=115200 debug / 上拉→console=null）
- inittab ttyS0 getty 已禁用（UART0 由 dji_rc 统一管理）
- getty_stop 用 `fuser -k /dev/ttyS0` 杀干净残留进程（含 login shell）

### 审查修复（已提交）
- g_crsf_stop 独立原子量（避免 t1/t2 误退）
- 退出死锁修复（join 前 close fd）
- g_out_baud 零值、out_mode 过期参数、getty 释放时序

### getty 修复（已提交）
- busybox 无 pkill → 用 killall
- getty_stop 增强：`fuser -k /dev/ttyS0` 杀所有占用 ttyS0 进程（含 getty 派生的 login shell）

### UDP 阻塞修复（v150，本次核心）
- send_rcmsg/send_tlm 阻塞 sendto 卡死主循环（sock_alloc_send_pskb）
- 修复：socket 设 O_NONBLOCK + sendto MSG_DONTWAIT，EAGAIN 忽略

## 八、重要决策及其理由

| 决策 | 理由 |
|---|---|
| UART0 释放为协议输出 | 只有 3 个 UART，协议输出必须用 UART0 |
| PB6 检测角色切换 | 一个 GPIO 让 UART0 一鱼两吃 |
| mmap 读寄存器 | 内核无 sysfs gpio，devmem 受限 |
| 页内偏移 0x800 | 0x01C20000 是 clock 区不是 pinctrl |
| dji_rc 统一管理 getty | 避免 S99 重复启动 |
| **每次检测重新 mmap** | 运行中同映射读到旧值，重映射读实时值 |
| **inittab getty 禁用** | 系统级 getty respawn 抢 UART0，杀不掉 |
| **UDP sendto 非阻塞** | 目标不可达时阻塞 sendto 卡死主循环，PB6 poll 失效 |

## 九、被否定的方案

| 方案 | 否定理由 |
|---|---|
| SPI env 存 bootcmd | CONFIG_ENV_IS_IN_FLASH 未启用，U-Boot 不读 |
| pread/pwrite /dev/mem | **读回全 0**，不可靠 |
| DTB bias-pull-up 为主 | 运行时未生效（读取方式问题）|
| U-Boot 启用 SPI env | 本次救火不依赖，后续优化 |

## 十、当前进度

- ✅ SBUS/CRSF 输出、通道映射、回传、App 配置：完成验证
- ✅ PB6 启动检测：正确
- ✅ **PB6 运行中自动切换：完整修复验证**（提交 `475c94e` + `1c0a9a2` + `4ba484b`）
- ✅ **主循环不再卡死**（UDP 阻塞修复，v150）
- ✅ **U-Boot bootcmd 115200**：已改 PB6 检测版
- ⚠️ OTA A/B 槽切换：不可用（见 docs/ota_ab_slot_issue.md）

## 十一、尚未完成的任务

1. ✅ **【已完成】修复 PB6 运行中切换**
   - 根因1：代码误落在已否定 pread（pread 读回全 0）→ 恢复 mmap 每次重映射（`475c94e`）
   - 根因2：inittab getty respawn + login shell 占 ttyS0 → 禁用 getty + fuser -k（`1c0a9a2`）
   - 根因3：UDP sendto 阻塞卡死主循环 → 非阻塞 socket（`4ba484b`）
   - 真机验证：运行中接地/断开多次往返切换正常
2. ✅ **【已完成】OTA A/B 槽切换验证**：连续 20 次 OTA 测试 20/20 成功
   - 每次上传 rootfs → 重启 → 正确切到另一槽（A↔B 往返）
   - **OTA 切槽完全正常**（之前"bootcmd 硬编码 A 槽不会切"的判断被实测推翻）
   - docs/ota_ab_slot_issue.md 的判断已过时，OTA 可用
3. **U-Boot 段乱码（低优先）**：冷启动 Booting Linux 前 U-Boot banner 乱码（115200/921600 都乱）。
   - 已排除：CONFIG_BAUDRATE=115200、SPL 115200、bootcmd 正确
   - 疑点：UART0 是 `snps,dw-apb-uart`，可能 DW 驱动波特率时钟计算错误
   - 待办：查 DW 驱动 APB2 时钟频率；或用 UART1/2 做 console 规避
4. 安装 App v1.3.0 到 DJI RC（需 adb 在线）
5. CRSF 模式实测（切 CRSF 输出 + 回传）

## 十二、不能随意修改的内容

1. **dji_rc.cpp 的 mmap 页内偏移 0x800**（必须保留）
2. **g_crsf_stop 独立原子量**（不能复用 g_stop 控 t3）
3. **退出顺序**：join 前 close fd（防死锁）
4. **getty 用 killall**（busybox 无 pkill）
5. **PB6 硬件默认上拉**（硬件已定，不能改接地语义）
6. **dji_rc 动态编译**（静态超分区 4.468MB）
7. S99 不能再用 devmem 读 PB6（交给 dji_rc 统一处理）
8. **每轮改动后 git commit**

## 十三、新会话接下来先做什么

1. **处理 OTA A/B 槽切换**（docs/ota_ab_slot_issue.md）：bootcmd 加槽切换 或 SPL fallback
2. 安装 App v1.3.0 到 DJI RC（需 adb 在线）
3. CRSF 模式实测（切 CRSF 输出 + 回传）
4. 全程保持"写后读回验证" + 每轮 git commit

## 十四、关键文件

- `ubuntu/src/dji_rc.cpp`：主守护进程（PB6 检测在此）
- `ubuntu/src/crsf.h/c`：CRSF 协议
- `ubuntu/src/rc_map.h/c`：通道映射
- `ubuntu/scripts/S99tun_nat_hub`：启动脚本
- `scripts/build_spi_image.py`：SPI 镜像构建（bootcmd PB6 检测）
- `docs/pb6_detection_retrospective.md`：问题复盘
- `docs/pb6_uart0_switch.md`：功能设计
- `docs/ota_ab_slot_issue.md`：OTA A/B 槽切换问题
- 最新提交: `475c94e`（PB6 mmap 修复）、`1c0a9a2`（getty_stop 增强）、`4ba484b`（UDP 非阻塞）

## 十五、固件产物 md5

| 文件 | md5 |
|---|---|
| dji_rc（v150 固化，UDP 非阻塞 + mmap 重映射）| `fad8b8f2` |
| web_server | `c56238ae` |
| rootfs_v150.squashfs | `de22318a` |
| spi_image_v150.bin | `ebc7486d` |
