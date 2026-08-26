# RC Input Contract 2026-08-26

## getevent 高频摇杆

- 设备路径: `/dev/input/event4`
- 设备名: `DJI embedded joystick`
- 权限: `crw-rw---- root input`; ADB shell 属于 `input` 组，可读。普通 APK 默认不属于 `input` 组，后续需真机 APK 权限验证。
- SELinux: `Permissive`
- 轴能力:
  - `ABS_X`: -32768..32767
  - `ABS_Y`: -32768..32767
  - `ABS_RX`: -32768..32767
  - `ABS_RY`: -32768..32767
  - `ABS_Z`: 0..255
  - `ABS_RZ`: 0..255
  - `ABS_HAT0X`: -1..1
  - `ABS_HAT0Y`: -1..1
- 实测确认轴映射:
  - CH1: `ABS_RX`
  - CH2: `ABS_RY`
  - CH3: `ABS_Y`
  - CH4: `ABS_X`
  - CH5: `ABS_RZ`
  - CH6: `ABS_Z`
- 实测确认按键映射:
  - REC: `BTN_TL`
  - SHOT: `BTN_TR`
- 补充按键设备:
  - 设备路径: `/dev/input/event3`
  - 设备名: `gpio-keys`
  - 能力: `KEY_F1`、`KEY_F2`、`KEY_F3`、`KEY_F4`、`KEY_F5`、`KEY_F6`、`KEY_VOLUMEUP`
  - 当前脚本映射: L1=`KEY_F1`、L2=`KEY_F2`、L3=`KEY_F3`、R1=`KEY_F4`、R2=`KEY_F5`、R3=`KEY_F6`
- 归一化:
  - -32768..32767 -> -1024..1023
  - 0..255 -> -1016..1024，以 127 为中位
- 动态样本状态:
  - 第一次息屏状态未收到事件。
  - 唤醒并 `svc power stayon true` 后，`timeout 30 getevent -lt /dev/input/event4` 成功抓到 5021 行。
  - 有效轴/键:
    - `ABS_RX`: 62 次，范围 `-31823..32171`
    - `ABS_RY`: 64 次，范围 `-23186..32766`
    - `ABS_HAT0X`: 12 次，范围 `-1..1`
    - `ABS_HAT0Y`: 12 次，范围 `-1..1`
    - `BTN_TR`: 2 次按下/抬起，对应 SHOT
    - `BTN_THUMBL`: 6 次按下/抬起
  - 初步判断: 这批动作主要覆盖右摇杆、方向键和两个按钮。
  - 后续仍需补抓: `ABS_X`、`ABS_Y`、`ABS_Z`、`ABS_RZ` 的动态样本，用于校准左摇杆和滚轮/拨轮物理方向。

## 40007 低频摇杆和按键

- 实测协议: TCP LISTEN，不是 UDP。
- 监听地址: `0.0.0.0:40007`
- 从 Windows 连接 `192.168.5.249:40007` 可建立 TCP 连接，但未主动推送数据。
- 发送 HTTP GET 和简单二进制探测包均无响应，说明 40007 不是裸流，也不是 HTTP；大概率需要 DJI 内部协议握手或特定 payload。
- ADB 本机读取已确认可用:
  - `adb -s 7XJCM630011XC9 exec-out toybox nc 127.0.0.1 40007`
  - 5 秒内可抓到连续 DUML 包，其中 `cmd_set=0x06/cmd_id=0xAE`、长度 30 的 RC 帧可按 V3s 115200 串口同一套 `RC/0xAE` 规则解码。
  - 因此脚本/APP 侧调试优先使用 ADB 本机源，不把 `192.168.5.249:40007` 当作电脑直连裸 TCP 流。
- 已确认 DUML 帧:
  - `cmd_set=0x06/cmd_id=0xAE`: 17 字节 payload，含 6 路摇杆、STOP/FOCUS/SHOT/REC/RTH、C1/C2/C3、方向键、DIAL、MODE。
  - `cmd_set=0x01/cmd_id=0x02`: 13 字节 payload，含低频 6 路摇杆和 STOP/FOCUS/SHOT/REC/MODE fallback。
  - `RC/0xAE` 解码后 CH5/CH6 需要对调才对应物理控件。

## 融合规则

1. 摇杆轴优先使用 getevent，fresh 窗口暂定 80ms。
2. getevent 轴超过 80ms 未更新时，回落到 40007 轴。
3. 按键、模式、拨轮优先使用 40007。
4. `getevent` 和 40007 都是输入更新源，不能作为输出节拍；Android 侧 publisher 必须按固定周期定时输出完整状态，当前周期为 20ms。
5. Android 侧融合结果编码为 `RCM1` 风格 RC 数据，App 页面和 V3s 输出链路都消费同一份统一 RC 状态。
6. V3s 旧双串口解码只保留为 fallback/诊断，不再作为新方案的正常摇杆来源。

## 调试脚本

- `scripts/rc_getevent_channels.py`: 单独观测 getevent 高频通道和 event3 L/R 按键。
- `scripts/rc_40007_serial_monitor.py`: 单独观测 40007/串口 DUML RC 帧。
- `scripts/rc_full_monitor.py`: 同时读取 getevent 与 ADB 本机 40007，输出 CH1..CH6、REC/SHOT、L1..L3、R1..R3、MODE、STOP、FOCUS、RTH、C1..C3、DIAL 等完整遥控状态。
  - 默认用法: `python scripts\rc_full_monitor.py -s 7XJCM630011XC9`
  - 变化流: `python scripts\rc_full_monitor.py -s 7XJCM630011XC9 --changes`
