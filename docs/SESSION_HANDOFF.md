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

### PB6 检测（启动时正确，运行中切换待修）
- dji_rc pb6_grounded()：mmap /dev/mem 读寄存器（页内偏移 0x800 已修复）
- S99：简化，PB6 由 dji_rc 统一处理
- U-Boot bootcmd：PB6 检测 console（115200/119000 待处理）
- DTB：bias-pull-up（辅助）

### 审查修复（已提交）
- g_crsf_stop 独立原子量（避免 t1/t2 误退）
- 退出死锁修复（join 前 close fd）
- g_out_baud 零值、out_mode 过期参数、getty 释放时序

### getty 修复（已提交）
- busybox 无 pkill → 用 killall

## 八、重要决策及其理由

| 决策 | 理由 |
|---|---|
| UART0 释放为协议输出 | 只有 3 个 UART，协议输出必须用 UART0 |
| PB6 检测角色切换 | 一个 GPIO 让 UART0 一鱼两吃 |
| mmap 读寄存器 | 内核无 sysfs gpio，devmem 受限 |
| 页内偏移 0x800 | 0x01C20000 是 clock 区不是 pinctrl |
| dji_rc 统一管理 getty | 避免 S99 重复启动 |

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
- ✅ **PB6 运行中自动切换：已修复并验证**（提交 `475c94e`）
- ⚠️ U-Boot 波特率 921600：未处理

## 十一、尚未完成的任务

1. ✅ **【已完成】修复 PB6 运行中切换**（提交 `475c94e`）
   - 根因：代码误落在复盘已否定的 pread 实现（pread 读回全 0）
   - 修复：pb6_grounded() 恢复 mmap，每次检测重新 open+mmap+munmap
   - 真机验证：接地/断开均实时切换，进程无崩溃
2. U-Boot CONFIG_BOOTCOMMAND 改 115200（解决 U-Boot 乱码 + 内核 921600）
3. 安装 App v1.3.0 到 DJI RC（需 adb 在线）
4. CRSF 模式实测（切 CRSF 输出 + 回传）

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

1. **处理 U-Boot CONFIG_BOOTCOMMAND 115200**（当前唯一剩余固件问题）
   - 解决 U-Boot 阶段波特率 921600 乱码 + 内核 console 波特率不一致
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
- 最新提交: `98b6131`（getty 修复）、`f78ce78`（mmap 偏移修复）

## 十五、固件产物 md5

| 文件 | md5 |
|---|---|
| dji_rc（mmap 每次重映射，PB6 运行中切换已修复）| `54e2a723` |
| web_server | `c56238ae` |
| rootfs_v146.squashfs | `7ba75ad5` |
| spi_image_v146.bin | `c96a2f69` |
