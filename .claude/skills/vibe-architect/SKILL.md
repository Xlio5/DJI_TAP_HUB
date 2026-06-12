---
name: vibe-architect
description: 多Agent架构设计 — 启动多个专业Agent并行评审架构方案，综合输出设计文档
---

# Vibe Architect — 多 Agent 架构设计

用户想做架构设计。你必须使用多 Agent 编排（Workflow 或并行 Agent）来完成。

## 设计流程

```
用户描述需求
    │
    ▼
┌─────────────┐
│ Phase 1: 理解  │ ← 单个 Agent 梳理需求、约束、边界
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Phase 2: 设计  │ ← 3 个 Agent 并行，从不同角度设计方案
│  A: MVP 优先   │     Agent 1: 最简可行方案，最快出活
│  B: 稳健优先   │     Agent 2: 企业级方案，关注可靠性
│  C: 性能优先   │     Agent 3: 高性能方案，关注延迟/吞吐
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Phase 3: 评审  │ ← 1 个 Agent 综合 3 个方案，评出最优
└──────┬──────┘
       │
       ▼
┌─────────────┐
│ Phase 4: 输出  │ ← 生成架构文档存入知识库
└─────────────┘
```

## 实现方式

### 方式 A：用 Workflow 编排（推荐）

```javascript
// 伪代码 — 实际在 Claude Code 中用 Workflow 工具
phase('需求分析');
const requirements = await agent('分析需求并提取约束', { schema: REQ_SCHEMA });

phase('并行设计');
const designs = await parallel([
    () => agent(`MVP 优先设计方案：${requirements}`, { model: 'haiku', label: 'mvp-design' }),
    () => agent(`稳健优先设计方案：${requirements}`, { model: 'sonnet', label: 'robust-design' }),
    () => agent(`性能优先设计方案：${requirements}`, { model: 'sonnet', label: 'perf-design' }),
]);

phase('综合评价');
const review = await agent(`综合评审 3 个方案，选出最优并说明理由：
  方案A(MVP): ${designs[0]}
  方案B(稳健): ${designs[1]}
  方案C(性能): ${designs[2]}
`, { schema: REVIEW_SCHEMA });

phase('生成文档');
// 将结果写入项目目录
```

### 方式 B：交互式（与用户对话）

如果用户偏好对话式设计，按以下流程：
1. 先问清楚项目定位、用户群体、性能要求
2. 给出 2-3 个方案（不要太多）
3. 每个方案说清楚：架构图（ASCII）、技术栈、优缺点、适合场景
4. 用户选择后，展开详细设计

## 典型架构场景

### 场景 1：Android APK + Linux 服务端

```
推荐架构：TCP 长连接 + Protocol Buffers

Android APK (Kotlin)
  ├── UI Layer (Jetpack Compose)
  ├── ViewModel (MVVM)
  ├── Repository (数据层)
  │   └── TcpClient (OkHttp / raw Socket)
  └── Native Lib (.so via NDK, 可选)
         └── 串口通信 (android-serialport-api)

Ubuntu 服务端 (C++ / Python)
  ├── TcpServer (Boost.Asio / asyncio)
  ├── SerialBridge (termios)
  ├── DataStore (SQLite)
  └── APIServer (REST / gRPC)

通信协议：Protobuf 或 JSON
数据格式：{ "cmd": "READ_SENSOR", "id": 1, "ts": 1234567890 }
```

### 场景 2：嵌入式桥接

```
STM32/ESP32 ←→ UART ←→ Radxa 5C ←→ TCP/WiFi ←→ Android

STM32：传感器采集 + 执行器控制
Radxa：协议转换 + 数据缓存 + 上行转发
Android：UI 显示 + 用户控制
```

## 输出要求

1. **架构图**（ASCII art）
2. **技术栈**（每层用什么语言/库）
3. **通信协议**（数据格式、错误处理）
4. **部署方案**（系统架构图、systemd 服务列表）
5. **文件存入** `20_项目/<项目名>/架构设计.md`

## 多 Agent 优势

- 3 个 Agent 并行设计 → 和串行比，时间约 1/3
- 不同视角捕获不同风险和机会
- 综合评审阶段发现单个方案的盲区
- 用在你的 DeepSeek V4 API：haiku 做 MVP（快），sonnet 做专业设计（稳）
