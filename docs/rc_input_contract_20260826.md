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
- 当前代码默认轴映射:
  - CH1: `ABS_X`
  - CH2: `ABS_Y`
  - CH3: `ABS_RX`
  - CH4: `ABS_RY`
  - CH5: `ABS_Z`
  - CH6: `ABS_RZ`
- 归一化:
  - -32768..32767 -> -1024..1023
  - 0..255 -> -1016..1024，以 127 为中位
- 动态样本状态: 已执行 `timeout 30 getevent -lt -c 80 /dev/input/event4`，当次未收到事件输出；后续需要在操作者明确拨动控件时再抓一次，校准 CH1..CH6 物理方向。

## 40007 低频摇杆和按键

- 实测协议: TCP LISTEN，不是 UDP。
- 监听地址: `0.0.0.0:40007`
- 从 Windows 连接 `192.168.5.249:40007` 可建立 TCP 连接，但未主动推送数据。
- 发送 HTTP GET 和简单二进制探测包均无响应，说明 40007 不是裸流，也不是 HTTP；大概率需要 DJI 内部协议握手或特定 payload。
- DJI APK 明文 proto 线索:
  - `AppSpecialControlJoyStickDataType.proto`
  - `AppVirtualStickDataType.proto`
- 已按两个 proto 增加解析支持:
  - `DJISpecialControllJoyStickStruct`: menu/playback/record、channel0..6、ioc/rs、button、shutter/focus/mode/gohome
  - `DJIGSJoystickData`: roll/pitch/yaw/throttle float
- 当前假设:
  - `DJISpecialControllJoyStickStruct` 对应低频按键 + 7 路 1 字节模拟通道。
  - `DJIGSJoystickData` 对应虚拟摇杆 float 控制量。
  - 40007 实际帧可能有长度头或封装头，后续抓到真实 payload 后再锁定包头。

## 融合规则

1. 摇杆轴优先使用 getevent，fresh 窗口暂定 80ms。
2. getevent 轴超过 80ms 未更新时，回落到 40007 轴。
3. 按键、模式、拨轮优先使用 40007。
4. Android 侧融合结果编码为 `RCM1` 风格 RC 数据，App 页面和 V3s 输出链路都消费同一份统一 RC 状态。
5. V3s 旧双串口解码只保留为 fallback/诊断，不再作为新方案的正常摇杆来源。
