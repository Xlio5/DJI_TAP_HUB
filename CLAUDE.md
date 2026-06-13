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

## 问题解决流程（重要）

**遇到问题时，先分析再动手，不要直接改代码：**

1. **分析阶段** — 收集日志、查状态、定位根因。用诊断脚本而非直觉判断。
2. **讨论阶段** — 向用户报告分析结果，说清楚根因是什么，给出方案选项（含利弊），让用户决策。
3. **实施阶段** — 用户确认后再动手改代码。

**禁止行为：**
- ❌ 看到报错就立即改代码，连续改多次还不行
- ❌ 不提供分析结论直接给修复方案
- ❌ 用户说"不行"就换一个方向盲目尝试

## 知识回流规则

开发中产生的知识**自动写入** Obsidian Vault。这是多项目知识积累的核心机制。

### 触发条件

以下情况必须回流到知识库：
- 解决了一个非显而易见的 bug 或错误
- 做出了架构/技术选型决策及理由
- 学到了新的 API、工具、模式用法
- 澄清了一个容易误解的概念
- 产出了可复用的代码片段或配置
- 用户明确说"记下这个"

### 目标路径

```
c:\Users\xlong\Documents\Obsidian Vault\00_收件箱\YYYY-MM-DD-{主题}.md
```

### 写入格式

```markdown
---
type: backflow
created: YYYY-MM-DD
source_project: TUN_NAT_HUB
topic: {主题}
status: captured
tags:
  - backflow
---

# {标题}

## 来源
- 项目: [[TUN_NAT_HUB]]
- 场景: {一句话描述讨论上下文}

## 要点
1. {核心结论}
2. {关键细节}

## 代码/配置（如有）
{可复用的片段}

## 关联
- {相关技术/概念}
- {相关笔记wikilink}
```

### 约束
- 每篇只记一个主题，保持原子化
- 中文撰写，技术术语保留英文
- 路径中的 {主题} 用英文短横线命名
- 写完后告诉用户"已回流到知识库"
- 之后在主 Vault 执行 `/ingest-backflow` 可将回流条目归档到 `30_研究/` 或 `40_知识库/`

## 可用的 Skills

| 命令 | 用途 |
|------|------|
| `/android-dev` | Android APK 初始化、编码、构建、签名、部署 |
| `/ubuntu-dev` | Ubuntu C++/Python 项目、systemd、交叉编译 |
| `/vibe-architect` | 多 Agent 并行架构设计 + 评审 |
