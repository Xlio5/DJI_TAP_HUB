# 开源仓库发布设计

## 目标

从当前内部开发仓库生成一个独立、干净、可直接添加 Git remote 后推送的公开仓库。公开仓库覆盖 Android App、Linux/V3s 服务、共享协议、通用脚本和完整技术文档，不携带内部历史、硬件设计、现场凭据或调试产物。

## 仓库形式

- 使用单一 Git 仓库维护整套软件。
- 新仓库目录名为 `tun-nat-hub-open-source`。
- 新仓库使用全新的 Git 历史，当前内部仓库及其历史保持不变。
- Android、Linux 和协议位于同一版本边界，避免跨仓库协议漂移。
- Linux 目录在公开仓库中命名为 `linux/`，由内部仓库的 `ubuntu/` 迁移而来。

## 公开内容

```text
tun-nat-hub-open-source/
├── android/
├── linux/
├── protocol/
├── docs/
├── scripts/
├── assets/
├── README.md
├── README.zh-CN.md
├── CONTRIBUTING.md
├── SECURITY.md
├── LICENSE
└── .gitignore
```

公开内容包括：

- Android Kotlin/Jetpack Compose 源码、Gradle Wrapper 和必要的本地构建依赖。
- Linux/V3s C/C++ 源码、CMake 配置、测试及通用运行脚本。
- 两端共享帧协议。
- 不包含主机地址、用户名或密码的通用构建与检查脚本。
- 双语项目介绍、部署手册、架构说明、协议说明、排障手册和代码地图。
- 项目标志和 README 所需公开图片。

## 明确排除

- `hardware/` 及所有 PCB、原理图、BOM、EasyEDA 文件和硬件规划资料。
- `backup/`、`tmp/`、`Testing/`、`ref/`、构建缓存和本机工具配置。
- APK、固件、rootfs、SPI 镜像、抓包、日志、设备转储和测试媒体。
- `.agents/`、`.claude/`、`AGENTS.md`、`CLAUDE.md` 等内部 AI 工作流。
- 真实现场 IP、用户名、密码、ADB key、SSH host key 和机器绝对路径。
- 版权归属不清晰的第三方二进制 APK。

## 许可证

- 采用 `GPL-3.0-only`。
- 根目录保存完整 GNU GPL v3 许可证文本。
- README 与贡献指南明确：分发修改版时必须继续提供 GPL 对应源代码。
- 不声明禁止商用，避免与 GPL 条款冲突。

## README 设计

- `README.md` 使用英文，作为 GitHub 默认首页。
- `README.zh-CN.md` 提供等价中文内容。
- 两份 README 顶部互相链接。
- 首页依次包含：项目定位、功能、系统总览图、适用平台、快速开始、构建、运行、文档索引、状态/限制、贡献、许可证和免责声明。
- 明确本项目为社区项目，与 DJI 无隶属、授权或背书关系。

## 文档与框图

使用 GitHub 原生 Mermaid，避免维护生成图片。至少提供以下五张图：

1. 系统总览：Android、USB、Linux/V3s、NAT 与 LAN 设备。
2. IP 数据流：VpnService/TUN、帧封装、USB、Linux TUN、MASQUERADE/DNAT。
3. 遥控数据流：DJI getevent 与 40007、网络 ADB、融合、RCMSG、CRSF/SBUS。
4. 启动时序：Android BootReceiver/前台服务、USB 枚举、Linux 服务和链路建立。
5. 模块关系：Android 模块、Linux 模块和共享协议的依赖边界。

## 安全清理

- 迁移采用文件白名单，不复制整个内部仓库。
- 扫描文本中的密码、token、私钥、真实 IP、用户名和 Windows 绝对路径。
- 扫描文件大小和扩展名，禁止意外提交发布二进制与调试产物。
- 保留示例地址时仅使用 RFC 5737 文档地址或变量占位符。
- 部署配置使用环境变量/命令参数，不内置凭据。

## 验证标准

- 新仓库 `git status` 干净，且只有一个准备公开的初始提交。
- Android `assembleDebug` 和 JVM 测试通过。
- Linux CMake 配置、构建及 CTest 通过；若主机依赖不足，明确记录验证范围。
- README 和文档中的相对链接全部存在。
- Mermaid 代码块语法完整。
- 敏感信息与大文件扫描无阻断项。
- 新仓库没有配置 remote，用户之后只需执行 `git remote add origin ...` 与 `git push`。

