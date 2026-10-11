# V3s ADB RC 输入模式设计

## 目标

把现有 RC 输入选择扩展为三个语义明确、可持久化的模式：

1. `android_fusion`：Android App 本地融合 `getevent + 40007`，通过 UDP 65531 发布 RCM1 给 V3s。
2. `v3s_serial`：V3s 使用 DJI 串口解析结果，Android 只接收 UDP 65530 回传。
3. `v3s_adb`：V3s 通过网络 ADB `10.0.0.2:5555` 读取 `/dev/input/event4`，Android 只接收 UDP 65530 回传。

`v3s_adb` 是无人值守默认值。DJI 与 V3s 开机后即使不打开 App，V3s 仍能建立 ADB getevent 采集并输出 RC。

## 架构选择

继续使用单一集成版 `dji_rc`，不维护独立的生产 `dji_rc_adb` 二进制。`dji_rc_adb` 只视为现场部署时的文件名；ADB client、串口解码和 App RCM1 接收都属于 `dji_rc`。

三个采集器可以同时保持就绪，但新增的显式输入模式只允许一个来源进入通道映射、UART 输出、状态文件和 UDP 65530 回传。模式切换不杀进程、不重启 CRSF bridge，避免输出瞬断和重复启动命令漂移。

## V3s 配置与接口

在 SPI 配置 JSON 中新增顶层字段：

```json
{
  "rc_input_mode": "v3s_adb"
}
```

允许值仅为 `android_fusion`、`v3s_serial`、`v3s_adb`。缺失或非法值回退到 `v3s_adb`。

`web_server` 新增：

- `GET /api/rc/input`：返回当前持久配置和 `dji_rc` 报告的实际活动源。
- `POST /api/rc/input`：接收 `{"mode":"..."}`，校验后写入 SPI；成功返回最终模式，非法值返回 HTTP 400。
- `/api/config` 同时包含 `rc_input_mode`，供 App 首次连接时同步。

`dji_rc` 启动时读取该字段，并在现有 2 秒配置轮询中热更新。状态 JSON 新增 `configured_input_mode`；`active_src` 继续表示当前实际生效来源，便于区分“配置为 ADB”与“ADB 尚未连接”。

## 来源选择规则

- `android_fusion`：只接受 App UDP 65531 的新鲜 RCM1；串口和 V3s ADB 数据不进入输出。
- `v3s_serial`：只接受串口融合结果；App RCM1 和 V3s ADB 数据不进入输出。
- `v3s_adb`：只接受 V3s ADB getevent 状态；串口和 App RCM1 数据不进入输出。
- 选中来源过期时输出无效 RC 状态，不自动回退到另一个来源，避免故障时控制权静默切换。

S99 启动参数保留 `v3s_adb` 作为旧配置兼容默认值；SPI 中存在合法模式时以 SPI 为准。

## Android 行为

`RcInputMode` 扩展为：

- `ANDROID_FUSION` / “安卓融合”
- `V3S_SERIAL` / “V3s 串口”
- `V3S_ADB` / “V3s ADB”

切换流程：

1. App 向 `POST /api/rc/input` 提交目标模式。
2. V3s 返回成功后，App 保存本地 preference 并重启本地 RC fusion runtime。
3. 仅 `ANDROID_FUSION` 启动 Android getevent 与 40007 融合；另外两种模式暂停本地融合。
4. 两种 V3s 模式都完整消费 UDP 65530 的 16 通道数据。
5. 请求失败时保持原模式，并在设置区域显示简短错误，不出现 UI 已切换但 V3s 未切换的分裂状态。

App 建立 VPN 后从 `/api/config` 同步 V3s 持久模式，V3s 配置是权威来源。

## 状态显示

- 安卓融合：显示本机 `getevent Hz`、`40007 Hz`。
- V3s 串口：显示 V3s `921600 Hz`、`115200 Hz`、`rcmsg Hz`。
- V3s ADB：显示 V3s `adb getevent Hz`、`rcmsg Hz`、实际活动源。

V3s ADB 的 getevent 事件率可能在摇杆静止时为 0；这不等于断线。连接状态由 ADB shell 是否在线和最近有效状态共同表达。

## 测试与验收

- Kotlin 单元测试覆盖三模式 preference 解析、通道选择、状态文案和失败回滚状态转换。
- C++ 测试覆盖配置缺失/非法回退、三模式严格选源、来源过期不跨源回退、热切换。
- Web API 测试覆盖 GET、合法 POST、非法 POST 与 SPI 保存结果。
- 真机依次切换三种模式，核对 App、`/tmp/rc_state.json`、进程日志与 UDP 频率一致。
- V3s ADB 模式下关闭或划掉 App，验证 V3s 仍持续采集；重启 V3s 后验证模式和 `active_src` 恢复。

## 发布约束

Android APK 与 V3s rootfs/OTA 必须作为同一轮版本发布，均使用带版本和时间戳的文件名、release 目录、manifest 与 SHA256。只更新 APK 不足以获得第三模式；只更新 V3s 固件则旧 App 无法显式选择模式。
