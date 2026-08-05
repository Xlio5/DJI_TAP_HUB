# PB6 检测问题完整复盘

> 日期: 2026-08-05
> 状态: **已修复并验证** (提交 `475c94e`)

## 一、功能目标

PB6 输入检测切换 UART0 角色：
- **PB6 上拉**（默认）→ UART0 输出 SBUS/CRSF 协议
- **PB6 接地** → UART0 作 debug 串口（getty 登录终端）

要求：**运行中**每 2 秒检测，连续 3 次确认后自动切换（防抖）。

## 二、验证过的事实（关键证据）

### 事实 1：物理电平变化正常
```
devmem 0x01C20834 读 PB DATA:
  上拉（断开接地）→ 0x00000040 (bit6=1)
  接地           → 0x00000000 (bit6=0)
```
**物理 PB6 电平变化完全正常**（devmem 能正确读到上拉/接地）。

### 事实 2：启动时检测 100% 正确
- 手动跑 dji_rc（新进程）：接地→grounded=1 debug 模式 ✓；上拉→grounded=0 协议模式 ✓
- **启动时 mmap 读到实时值**

### 事实 3：运行中切换失效（核心 bug）
- 运行中的 dji_rc 每 2 秒 poll，**从不变更 grounded 判断**
- mmap 版：启动读到 0x40（上拉），之后一直 0x40，接地后仍读到 0x40 → 不切换
- pread 版：启动读到 0（误判接地），之后一直 0 → 不切换

### 事实 4：pread /dev/mem 读回全 0
```
pread 版首次检测: CFG1=0x00000000 PU0=0x00000000 DATA=0x00000000 grounded=1
```
pread 读所有寄存器都是 0 —— **pread /dev/mem 在这个 V3s 上不可靠**（或偏移换算有问题）。

### 事实 5：mmap 页内偏移 0x800 是必须的
- 0x01C20800 & ~0xFFF = 0x01C20000（clock 区）
- 必须加页内偏移 0x800 才到 pinctrl（0x01C20800）
- **修复后 mmap 启动检测正确**

## 三、走过的弯路

### 弯路 1：怀疑 DTB 上拉没生效
- 做法：DTS 加 `bias-pull-up` + 重编 DTB
- 结果：DTB 确认含上拉，但**运行时 PB6 仍读 0**
- **真因**：不是 DTB 问题，是**读取方式/地址问题**

### 弯路 2：改 CONFIG_BAUDRATE 但 U-Boot 仍 921600
- 做法：改 U-Boot .config CONFIG_BAUDRATE=115200
- 结果：U-Boot 自身 baudrate=115200，但**嵌入 env 的 bootcmd 仍 921600**（CONFIG_BOOTCOMMAND 没改）
- **真因**：U-Boot 用编译嵌入 env，CONFIG_ENV_IS_IN_FLASH 未启用，SPI env 不生效

### 弯路 3：mmap 页对齐后忘加页内偏移
- 做法：`mmap(0x01C20000)` 后直接 +0x28/+0x34/+0x40
- 结果：读到 clock 区（CFG1=0x90041811），不是 pinctrl
- **真因**：漏了 0x800 页内偏移 → **修复后启动检测正确**

### 弯路 4：怀疑运行中 mmap cache，改 pread
- 做法：pread/pwrite /dev/mem 替代 mmap
- 结果：**pread 读回全 0**（更糟），运行中仍不切换
- **真因**：pread /dev/mem 在 V3s 上不可靠

## 四、当前卡点 → 已修复

**根因（老大定位）**：不是 PB6 硬件、不是 DTB、不是 mmap cache——而是**代码误落在复盘已否定的 pread 实现上**。pread/pwrite /dev/mem 在 V3s 上读回全 0，导致运行中 poll 读到假 grounded，切换失效。

**修复（提交 `475c94e`）**：`pb6_grounded()` 恢复 mmap 方案，**每次检测重新 open+mmap+munmap**（新虚拟地址映射同一物理页），强制 input+pull-up 后读 DATA bit6。

**真机验证通过**（完整时序）：
```
上拉:     DATA=0x40 grounded=0 (协议模式)
接地:     DATA=0x00 grounded=1 → 连续3次确认 → "PB6 变化 → debug 模式"
断开:     DATA=0x40 grounded=0 → 连续3次确认 → "PB6 变化 → 协议模式"
再接地:   DATA=0x00 grounded=1 → 再次切回 debug ✓
```
进程全程存活，无崩溃。正式版 md5 `54e2a723`。

## 五、想法验证结果

| 想法 | 结果 |
|---|---|
| 1. mmap 每次检测重新映射 | ✅ **采用**。真机验证运行中能实时读 PB6 电平，切换完整通过 |
| 2. 内核 gpio sysfs | ❌ 未采用（内核未启用，且 mmap 已够用） |
| 3. ioremap 语义 / ioctl | ❌ 未采用 |
| 4. U-Boot 层配置 PB6 | ❌ 未采用（不能解决运行中检测） |
| 5. 换引脚 | ❌ 未采用（硬件已定 PB6） |

## 六、剩余待办

1. ✅ ~~验证 mmap 每次重映射~~ → **已修复验证**
2. ~~确认 gpio sysfs~~ → 不再需要
3. ~~回退 mmap 版~~ → 已完成
4. **U-Boot CONFIG_BOOTCOMMAND 的 921600 问题**（未处理，后续优化）

## 七、参考

- 功能设计: `docs/pb6_uart0_switch.md`
- 排查记录: `docs/pb6_uart0_debug_troubleshooting.md`
- 相关提交: `98b6131`, `f78ce78`, `83b1916`, `b45133a`
