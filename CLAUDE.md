# TUN_NAT_HUB — Vibe Coding 全栈项目

> Android APK (TUN/VPN) + Ubuntu 服务端 (NAT/Hub) 的 AI 驱动开发。

## 项目结构

```
TUN_NAT_HUB/
├── CLAUDE.md              ← 这个文件
├── .claude/               ← 本地 Skills + Settings
│   ├── settings.json      ← 权限配置
│   └── skills/
│       ├── android-dev/   ← Android 全流程
│       ├── ubuntu-dev/    ← Ubuntu 系统开发
│       └── vibe-architect/← 多 Agent 架构
├── android/               ← Android APK 项目
├── ubuntu/                ← Ubuntu 服务端（C/C++）
├── protocol/              ← 通信协议定义
├── docs/                  ← 项目文档
│   └── architecture.md
└── scripts/               ← 构建和部署脚本
```

## Agent 角色定义

开发时使用 Claude Code 内置的 `Workflow` / `Agent` 工具：

### Android 工程师
```
你是 Android 开发专家。使用 Kotlin + Jetpack Compose。
能力：TUN 接口/VPN Service、网络层、APK 构建。
项目在 android/ 目录。
每次修改后确认 ./gradlew assembleDebug 通过。
```

### Ubuntu 工程师
```
你是 Linux C++ 开发专家。使用 C++17 + CMake + Boost.Asio。
能力：TUN 虚拟网卡、NAT 转发、多客户端 Hub 管理。
目标架构：ARM64 (RK3588) + x86_64。
项目在 ubuntu/ 目录。
每次修改后确认 cmake --build build/ 通过。
```

### 代码审查员
```
你是代码审查专家。审查 Kotlin 和 C++ 代码的：
1. 内存安全（C++: 智能指针、RAII）
2. 线程安全（Android: 主线程 vs IO 线程）
3. TUN 数据包处理正确性
4. NAT 状态一致性
5. 错误处理完整性
```

## 工作流

```
/vibe-architect  →  [Android Engineer ∥ Ubuntu Engineer]  →  Code Reviewer  →  部署
    架构设计              并行开发（git worktree隔离）           审查通过才能合
```

## 开发规范

- Kotlin 遵循 Android Kotlin Style Guide
- C++ 使用 Google C++ Style Guide
- Git commit: `feat(android|ubuntu|protocol): 描述`
- 所有注释使用中文

## 知识回流

开发中产生的知识写入 Obsidian Vault：
- 技术笔记 → `40_知识库/嵌入式/`
- 项目进展 → `20_项目/Vibe-Coding-全栈开发.md`

## 可用的 Skills

| 命令 | 用途 |
|------|------|
| `/android-dev` | Android APK 初始化、编码、构建、签名、部署 |
| `/ubuntu-dev` | Ubuntu C++/Python 项目、systemd、交叉编译 |
| `/vibe-architect` | 多 Agent 并行架构设计 + 评审 |
