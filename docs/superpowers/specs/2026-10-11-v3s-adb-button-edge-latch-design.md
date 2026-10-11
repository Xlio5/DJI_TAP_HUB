# V3s ADB Button Edge Latch Design

## Goal

避免 ADB getevent 的短按在 20ms 融合发布周期之前完成 `DOWN -> UP`，导致按下边沿完全丢失；同时接入 event3 的 `KEY_F1..F6`。

## Design

- getevent shell 读取所有 input 设备；摇杆轴仍只接受配置的 `/dev/input/event4`。
- 已知按键接受 event4 的 `BTN_TL/BTN_TR` 和 event3 的 `KEY_F1..F6`，分别映射 REC/SHOT 和 L1..R3。
- getevent 与 40007 各自维护入口按键锁存器。采集线程一看到高电平，立即把对应截止时间更新为当前时间后 120ms。
- 50Hz 发布线程先把入口锁存应用到两路状态，再执行既有融合；融合后保留最终按键保持，确保 Android UI 至少收到多帧按下状态。
- 不改变摇杆轴优先级、40007 字段映射、RCMSG 协议和三模式单源策略。

## Testing

- 单测覆盖 event3 F1-F6 解析与映射，以及 event4 过滤仍对轴生效。
- 单测模拟 `DOWN` 和 `UP` 都发生在下一次发布前，验证入口锁存仍输出按下。
- 运行 Ubuntu 全量构建并在 V3s 上验证版本、40007/RCMSG 频率与按键状态。
