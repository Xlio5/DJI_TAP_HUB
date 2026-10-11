# V3s ADB Button Edge Queue Design

## Goal

避免 ADB getevent 或 40007 的 `DOWN -> UP` 被“最新状态”覆盖，同时保持设备上报的真实按下时长，不使用固定时间锁存。

## Design

- getevent shell 读取所有 input 设备；摇杆轴仍只接受配置的 `/dev/input/event4`。
- 已知按键接受 event4 的 `BTN_TL/BTN_TR` 和 event3 的 `KEY_F1..F6`，分别映射 REC/SHOT 和 L1..R3。
- getevent 与 40007 各自维护容量 32 的按键边沿队列，只在 21 位按键掩码变化时保存完整状态。
- 50Hz 发布线程每周期按顺序消费一项边沿，保证按下帧先于释放帧输出；无边沿时继续发布最新轴状态。
- Android UI pump 同样维护容量 32 的边沿队列，按顺序应用按下和释放；稳定帧仍只保留最新值。
- 不改变摇杆轴优先级、40007 字段映射、RCMSG 协议和三模式单源策略。

## Testing

- 单测覆盖 event3 F1-F6 解析与映射，以及 event4 过滤仍对轴生效。
- 单测模拟 `DOWN` 和 `UP` 都发生在下一次发布前，验证 V3s 和 Android 均按原顺序消费两帧。
- 运行 Ubuntu 全量构建并在 V3s 上验证版本、40007/RCMSG 频率与按键状态。
