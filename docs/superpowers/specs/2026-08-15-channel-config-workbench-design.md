# 通道设置工作台设计

## 背景

当前 App 遥控页已有「通道配置」卡片，能读取和保存 V3s 的 `rc_output` 配置，包括输出协议、通道映射和 `src_cfg` 输入源微调。现有界面偏表单折叠，不像遥控器配置工具。

参考 `app参考/` 的 F20 助手截图后，确定采用其内容组织方式：通道设置以 CH1-CH16 行表格为主体，source 选择、实时值、反向、范围集中在同一行；但视觉风格保持 TUN_NAT_HUB 的暗色专业仪表盘，而不是照搬浅色面板。

## 目标

1. 把遥控页的通道配置从折叠表单改为「通道设置工作台」。
2. 主体按 CH1-CH16 行展示：通道号、source 按钮、当前输出值刻度、反向开关、范围输入。
3. 点击 source 按钮弹出「控件选择」面板，按摇杆旋钮、开关按键、功能键分组。
4. 保留现有固件 API 和数据结构，不改 V3s 协议。
5. 使用暗色系视觉：深蓝黑背景、蓝色高亮、低对比边框、大号触控控件。

## 非目标

1. 不重做整个 App 导航。
2. 不修改 `rc_output` / `src_cfg` 的固件 JSON 协议。
3. 不新增配置文件导入导出功能的真实持久化；顶部「载入配置 / 配置另存 / 参数管理」先做为界面入口，可在后续版本接入。
4. 不改变 CRSF-Lua ELRS 参数页。

## 交互设计

### 顶部操作区

通道设置工作台顶部提供四个大按钮：

- 默认配置：把通道映射和 `src_cfg` 恢复到 App 内默认值。
- 载入配置：保留入口，初版可显示未接入提示。
- 配置另存：保留入口，初版可显示未接入提示。
- 参数管理：保留入口，初版可滚动到输入源微调区或显示提示。

顶部同时显示当前输出协议选择：`SBUS / CRSF`。保存时继续写入 `rc_output.mode`。

### 通道行

每行展示一个输出通道：

- `CHx`：输出通道号。
- source 按钮：显示当前输入源，如 `J1`、`S1`、`mode`、`rec`。点击打开选择弹窗。
- 刻度条：显示该通道当前估算输出值，默认 1500；如果能从实时 `RcMsg` 推导 source 值，就显示实时值。
- 反向开关：绑定该 source 的 `_rev` 配置；无反向配置的 source 显示禁用状态。
- 范围输入：显示 min/max，例如 `1050,1950`；保存时拆成对应 source 的 `_min/_max` 配置。对开关类 source 显示开/关值。

### 控件选择弹窗

source 按钮弹窗采用参考图的「控件选择」结构，但暗色化：

- 摇杆&旋钮：`J1`-`J6`、`V1`、`V2`。
- 开关/按键：`L1`-`L3`、`R1`-`R3`、`K1`-`K4`、`S1`-`S4`。
- 功能键：`T1`-`T4`、飞行模式、拍照/录像、C1/C2、方向键等项目中已有 source。

选择后立即更新该通道 source，但只有点击保存才写入 V3s。

## 数据流

1. 进入遥控页后读取 `GET /api/config`。
2. 解析 `rc_output.mode`、`rc_output.map`、`rc_output.src_cfg`。
3. 初始化工作台状态：`mode`、`channelSources`、`srcCfg`。
4. 用户修改 source、范围、反向或协议。
5. 点击保存后按现有格式提交：

```json
{
  "rc_output": {
    "mode": "crsf",
    "map": "ch1,ch2,ch3,ch4,...",
    "src_cfg": {
      "st1_min": 1050,
      "st1_max": 1950,
      "st1_rev": 0
    }
  }
}
```

## 实现范围

主要修改：

- `android/app/src/main/java/com/tunnathub/app/MainActivity.kt`
  - 重构 `RemoteChannelConfig()`。
  - 新增通道工作台 Composable：通道行、source 选择弹窗、暗色按钮、范围编辑。
  - 复用现有 `SRC_CFG_GROUPS`、`SrcCfgRow`、`apiGet`、`apiPost`、JSON 解析函数。
- `android/app/build.gradle.kts`
  - 版本递增到 `versionName = "1.6.17"`、`versionCode = 56`。

不修改：

- `ubuntu/src/*`
- `protocol/*`
- CRSF-Lua 参数页相关文件

## 错误处理

- 读取配置失败：显示「读取失败」，继续保留默认映射，不阻塞遥控页实时数据显示。
- 固件不支持 `src_cfg_names`：隐藏高级范围/反向编辑，只允许通道 source 映射和协议选择。
- 保存失败：保留本地编辑状态，显示失败信息。
- 输入范围无效：保存前限制到 800-2200，min 大于 max 时自动交换。

## 验证

1. `./gradlew.bat testDebugUnitTest` 或可用的现有 Android 单元测试。
2. `./gradlew.bat assembleDebug` 构建 APK。
3. 静态检查界面文字：长文本不挤出按钮，CH1-CH16 在 DJI RC 横屏宽度可滚动浏览。
4. 若设备在线，安装到 DJI RC 并验证：
   - 能读取当前 `rc_output`。
   - 修改 CH source 后保存，V3s API 读回一致。
   - 修改范围/反向后保存，V3s API 读回一致。

## 后续可扩展

1. 接入真实配置文件导入/另存。
2. 把 source 当前值完全绑定实时 `RcMsg`，让每行刻度条跟随遥控输入。
3. 增加模板管理：AETR、TAER、自定义、飞控常用模式。
