# Plan: 全志 V3s 平台移植 — Phase 0: 环境搭建

**Source PRD**: `.claude/prds/v3s-porting.prd.md`
**Selected Milestone**: #1 — Phase 0: 环境搭建
**Complexity**: Medium

## Summary

在 X86 开发机上搭建全志 V3s 的完整交叉编译环境（Buildroot + ARMv7 musl toolchain），制作最小系统镜像并验证 V3s 开发板启动成功，确认 USB OTG Device 模式可用（`/sys/class/udc/` 存在）。这是整个 V3s 移植的基础 — 环境不对，后续所有工作无法开展。

## Patterns to Mirror

| Category | Source | Pattern |
|---|---|---|
| Naming | `ubuntu/CMakeLists.txt:5` | `project(usb_tund VERSION 1.0.0 LANGUAGES CXX)` — 小写+下划线命名 |
| Errors | `ubuntu/src/tun_iface.cpp:30` | `throw std::runtime_error("描述: " + std::string(strerror(errno)))` — 异常+errno描述 |
| Errors (shell) | `ubuntu/scripts/setup_gadget.sh:4` | `set -e` + `\|\| true` for non-critical cleanup |
| Logging (C++) | `ubuntu/src/main.cpp:175` | `std::cout << "=== TAG ==="` + `[TAG] 描述` 前缀格式 |
| Logging (shell) | `ubuntu/scripts/setup_nat.sh:12` | `echo "=== TUN_NAT_HUB NAT Setup ==="` |
| Build (CMake) | `ubuntu/CMakeLists.txt:7-9` | C++17, `-Wall -Wextra -Wpedantic`, `install(TARGETS ... DESTINATION ...)` |
| SSH (Python) | `scripts/probe_v3s.py:1-37` | paramiko + 尝试多组凭证 + `get_pty=True` + `recv_ready()` 轮询 |
| Platform detect | `ubuntu/CMakeLists.txt:20-24` | `CMAKE_SYSTEM_PROCESSOR MATCHES "aarch64\|arm"` |

## Files to Change

| File | Action | Why |
|---|---|---|
| `configs/v3s_buildroot_defconfig` | **CREATE** | V3s 最小系统 Buildroot 配置（内核+必需包列表） |
| `ubuntu/cmake/toolchain-armv7-musl.cmake` | **CREATE** | ARMv7 交叉编译工具链定义文件 |
| `scripts/cross_build_v3s.sh` | **CREATE** | 一键交叉编译脚本（cmake configure + build） |
| `scripts/probe_v3s.py` | **UPDATE** | 增强诊断输出（添加 g_serial/tun/netfilter 驱动状态检测） |
| `docs/v3s-deploy.md` | **CREATE** | V3s 环境搭建和部署文档（Phase 4 完整版的前置草稿） |

## Tasks

### Task 0.1: 确认 V3s 硬件就绪
- **Action**: SSH 登录 V3s 开发板（LicheePi Zero + ETH 底板），执行 `probe_v3s.py` 收集系统信息，确认：CPU 型号、内核版本、内存大小、USB UDC 路径、以太网接口名称、现有驱动模块列表、iptables 可用性
- **Mirror**: `scripts/probe_v3s.py` — 多凭证尝试 + `get_pty=True` + 结构化诊断输出
- **Validate**: `python scripts/probe_v3s.py` 成功返回系统信息，确认 `arch=armv7l`、`/sys/class/udc/` 非空、至少一个网络接口有 IP

### Task 0.2: 搭建 Buildroot + 交叉编译 toolchain
- **Action**: 下载 Buildroot (推荐 2024.02.x LTS)，使用 `configs/v3s_buildroot_defconfig` 构建包含 musl toolchain 的最小系统（目标：内核 + musl libc + python3 + iptables + dropbear + eudev）。构建产物：`arm-linux-gnueabihf-g++` toolchain + 最小 rootfs 镜像
- **Mirror**: `ubuntu/CMakeLists.txt:20-24` — `CMAKE_SYSTEM_PROCESSOR MATCHES` 平台检测模式
- **Validate**: `arm-linux-gnueabihf-g++ --version` 返回版本号；toolchain 可编译 hello world ARMv7 二进制

### Task 0.3: 编写交叉编译 toolchain file + 编译脚本
- **Action**: 创建 `ubuntu/cmake/toolchain-armv7-musl.cmake`（指定 `CMAKE_SYSTEM_NAME Linux`, `CMAKE_SYSTEM_PROCESSOR arm`, musl 交叉编译器路径, sysroot 路径），创建 `scripts/cross_build_v3s.sh`（调用 cmake + toolchain file + make）
- **Mirror**: CMakeLists.txt 现有结构 — 保持 `-Wall -Wextra -Wpedantic` + `-O2` + `C++17`。toolchain file 遵循 `SET(CMAKE_...)` 大写约定
- **Validate**: `bash scripts/cross_build_v3s.sh` 产生 `usb_tund` ARMv7 ELF 二进制；`file build_v3s/usb_tund` 输出 `ARM, EABI5`

### Task 0.4: 内核配置 — 勾选 USB Gadget / TUN / Netfilter
- **Action**: 基于 Buildroot 内核配置，启用：`CONFIG_USB_GADGET=y`, `CONFIG_USB_G_SERIAL=m`, `CONFIG_TUN=y`, `CONFIG_NETFILTER_XTABLES=y`, `CONFIG_NF_NAT=y`, `CONFIG_NF_CONNTRACK=y`, `CONFIG_IP_NF_IPTABLES=y`, `CONFIG_IP_NF_NAT=y`, `CONFIG_WATCHDOG=y`。写入 `configs/v3s_buildroot_defconfig` 的 kernel 配置片段。
- **Mirror**: 遵循 Buildroot 的 `BR2_LINUX_KERNEL_CONFIG_FRAGMENT_FILES` 机制（而非手改 `.config`）
- **Validate**: 构建完成后，`modprobe g_serial` 产生 `/dev/ttyGS0`，`modprobe tun` 成功，`iptables -L` 正常输出

### Task 0.5: 制作并烧写最小系统镜像
- **Action**: 使用 Buildroot 产出的 rootfs + 内核制作 SD 卡镜像。在 V3s 板上启动，通过串口（UART0 115200 8N1）或 SSH (dropbear) 登录，验证：系统启动成功、网络接口有 IP、`/sys/class/udc/` 存在
- **Mirror**: 无直接对应（这是全新操作），但要记录关键命令到 `docs/v3s-deploy.md`
- **Validate**: SSH 连接 V3s 成功，`uname -a` 显示 `armv7l`，`free` 显示 ~64MB，`ls /sys/class/udc/` 非空

### Task 0.6: 验证 USB OTG Device 模式 + g_serial 驱动
- **Action**: 在 V3s 上手动加载 g_serial：`modprobe g_serial use_acm=0 use_obex=0 idVendor=0x0BDA idProduct=0x8812`，确认 `/dev/ttyGS0` 出现。如果 MUSB 控制器行为异常（与 DWC3 不同），记录差异并评估 fallback 方案（configfs FunctionFS）。
- **Mirror**: `ubuntu/scripts/setup_gadget.sh` 的 g_serial 加载逻辑 — `modprobe g_serial use_acm=0 use_obex=0 idVendor=0x0BDA idProduct=0x8812` + `sleep 2` + `/dev/ttyGS0` 检测
- **Validate**: `ls -l /dev/ttyGS0` 显示字符设备；`cat /sys/kernel/config/usb_gadget/` 目录存在（configfs fallback 就绪）

## Validation

```bash
# 1. Toolchain 可用性
arm-linux-gnueabihf-g++ --version

# 2. 交叉编译通过 (Phase 1 验证，Phase 0 只验证 toolchain 工作)
echo 'int main(){}' | arm-linux-gnueabihf-g++ -x c++ - -o /tmp/test_v3s
file /tmp/test_v3s
# 期望: ELF 32-bit LSB executable, ARM, EABI5

# 3. V3s 系统状态
python scripts/probe_v3s.py
# 期望: arch=armv7l, /sys/class/udc/ 非空, free ~64MB

# 4. USB Gadget 可用性
# SSH 到 V3s 执行:
# modprobe g_serial use_acm=0 idVendor=0x0BDA idProduct=0x8812
# ls /dev/ttyGS0
# 期望: /dev/ttyGS0 存在
```

## Open Decisions (Blocking)

These are the 7 open questions from the PRD. **Phase 0 answers 3 of them** (D1, D2, D6); the rest are deferred to Phase 1+.

| # | Question | Phase 0 Action |
|---|----------|---------------|
| D1 | 开发板选型？ | **Task 0.1 确认** — 假设 LicheePi Zero + ETH 底板，如果不满足则换 |
| D2 | Buildroot vs Yocto？ | **Task 0.2 锁定** — 采用 Buildroot（PRD 建议） |
| D6 | g_serial 在 MUSB 上是否兼容？ | **Task 0.6 验证** — 最高风险项，必须 Phase 0 确认 |
| D3-D5, D7 | PHY/libc/链接/Python | Phase 1 再决定 |

## Risks

| Risk | Likelihood | Phase 0 Mitigation |
|---|---|---|
| V3s 板硬件问题（无法启动/网络不通） | Medium | Task 0.1 第一时间验证；备用：自备另一块 LicheePi Zero |
| Buildroot 构建耗时过长（首次全量 2-4h） | High | 后台构建 + 使用预编译 toolchain (bootlin.com) 加速 |
| MUSB 控制器不支持 g_serial `use_acm=0` | Medium | Task 0.6 优先验证；fallback: configfs FunctionFS（代码已有 `usb_gadget.cpp`） |
| 64MB 内存 Buildroot python3 放不下 | Medium | Task 0.2 构建后检查 rootfs 大小；如超限则降级到 micropython 或 Lua |
| 交叉编译 toolchain 版本不匹配（musl 版本太老） | Low | Task 0.2 使用 Buildroot 自带 toolchain（版本锁定） |

## Acceptance

- [ ] V3s 开发板可通过 SSH 访问，`uname -a` 显示 `armv7l`
- [ ] Buildroot 环境可复现构建（有 defconfig 文件）
- [ ] `arm-linux-gnueabihf-g++` 可编译 C++17 代码
- [ ] `usb_tund` 交叉编译为 ARMv7 ELF（Phase 1 验证，Phase 0 只验证 toolchain 工作）
- [ ] `/sys/class/udc/` 目录非空
- [ ] `modprobe g_serial` 可产生 `/dev/ttyGS0`（或记录 MUSB 不兼容的证据 + fallback 方案）
- [ ] 诊断脚本 `probe_v3s.py` 增强完成
- [ ] `docs/v3s-deploy.md` 草稿记录 Buildroot 构建步骤 + 烧写步骤
