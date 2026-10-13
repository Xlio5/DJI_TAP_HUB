# DJI 遥控器 — 开机自启 App 控制

> 更新: 2026-10-13
> 脚本: [`scripts/dji-rc/`](../scripts/dji-rc/)（`dji-autostart.ps1` 通用版 / `dji-agras.ps1` rc701 专用）
> 实测机型: **DJI RC Plus 2（rc701）**，固件 `V01.29.00.07`，Android 11

---

## 一、为什么需要

DJI 遥控器（RC / RC Plus / RC Plus 2 / RC Pro / RC2 / Smart Controller 等）开机后会
**自动拉起 DJI 官方 App**（rc701 出厂是农业 App `com.dji.agrasx`），一开机就进 DJI 界面，
挡住我们自己的 App（`com.tunnathub.app`）。

本方法**取消它的开机自启，但保留 App 可手动打开**——开机停在桌面，我们的 App 可以正常用。

**不需要 root**，普通 adb shell 权限即可（`setprop` / `pm disable-user` 均实测可用）。

---

## 二、原理

DJI 固件里，**开机自动拉起哪个 App 由系统属性决定**：

```
persist.dji.default_app = <包名>
```

DJI 定制的启动器读这个属性并拉起对应 App。该启动器**对外伪装成 `com.android.launcher3`**，
实际来自 `/product/priv-app/dpad_launcher`（查 `dumpsys package com.android.launcher3` 的
`codePath` 才能看到真身）。

| 目标 | 做法 |
|---|---|
| **取消自启，App 保留可手动打开** | 把属性改成**启动器自己**（`com.android.launcher3`）→ 开机停在桌面 |
| 恢复原样 | 属性写回原包名（脚本从 `dji-autostart.state` 读） |
| 属性不可写 / 想彻底关 | `pm disable-user --user 0 <包名>`（兜底，App 无法手动打开） |

两个关键点：
1. **属性值就是那个自启 App 的包名**——任何机器上都不用猜。
2. `persist.` 前缀属性写在 `/data/property`，**重启不丢**，一次设置长期有效。

> ⚠️ **唯一会失效的情况**：DJI 固件 OTA 升级后属性可能被覆盖回原值，重新设一次即可。

---

## 三、实测属性快照（rc701，已取消自启）

本机当前状态（`adb shell getprop | grep persist.dji`）：

| 属性 | 当前值 | 说明 |
|---|---|---|
| **`persist.dji.default_app`** | **`com.android.launcher3`** | **开机自启的 App（已改为启动器 = 自启关闭）** |
| `persist.dji.boot_apks_ctrl` | `1` | 开机启动 App 总开关（1=开）|
| `persist.dji.uav` | `ag801` | 机型标识（农业版）|
| `persist.dji.role` | `6` | 设备角色 |
| `persist.dji.is_first_launch` | `0` | 非首次启动 |
| `persist.dji.feat.native` | `com_key` | 定制特性开关 |
| `persist.dji.auto_trim_application` | `0` | 自动 trim 应用（未启用）|

设备识别：
```
ro.product.model         = DJI RC PLUS 2
ro.build.display.id      = V01.29.00.07 release-keys
ro.product.manufacturer  = DJI
启动器 (HOME)            = com.android.launcher3/.uioverrides.QuickstepLauncher
```

---

## 四、用法

### 脚本（推荐，`scripts/dji-rc/dji-autostart.ps1`）

不写死包名，自动从 `persist.dji.default_app` 读目标 App，可搬到其他 DJI 遥控器。

```powershell
# 0) 新机器先排查（强烈建议）
.\dji-autostart.ps1 discover

# 1) 查看当前状态
.\dji-autostart.ps1 status

# 2) 取消自启（原值存入 dji-autostart.state，可恢复）
.\dji-autostart.ps1 off -Reboot

# 3) 恢复自启
.\dji-autostart.ps1 on

# 4) 兜底：彻底禁用 / 解除 / 临时强停
.\dji-autostart.ps1 disable
.\dji-autostart.ps1 enable
.\dji-autostart.ps1 kill
```

其他机型 / 其他 DJI App（脚本没猜到时用 `-Package`）：

```powershell
.\dji-autostart.ps1 off -Package com.dji.industry.pilot   # DJI Pilot 2
.\dji-autostart.ps1 off -Package dji.go.v5                # DJI Fly
.\dji-autostart.ps1 off -Package com.dji.agrasx           # Agras 农业
```

> `dji-agras.ps1` 是 rc701 专用简化版（写死 `com.dji.agrasx` → `com.android.launcher3`），
> 模式名 `autostart-off` / `autostart-on`。

### 手动命令（不用脚本）

```powershell
# 看自启的是谁
adb shell getprop persist.dji.default_app

# 看启动器是谁（作为安全的替代值）
adb shell cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.HOME

# 取消自启（值改成启动器包名），然后重启
adb shell setprop persist.dji.default_app com.android.launcher3
adb reboot

# 恢复（写回原包名）
adb shell setprop persist.dji.default_app com.dji.agrasx

# 兜底：彻底禁用 / 恢复（不需要 root）
adb shell pm disable-user --user 0 com.dji.agrasx
adb shell pm enable com.dji.agrasx

# 临时关掉当前实例（重启后仍会自启）
adb shell am force-stop com.dji.agrasx
```

---

## 五、换一台新机器，怎么自己排查

按顺序跑，基本 5 分钟定位：

```powershell
# 1. 是不是 DJI 遥控器 + 安卓版本
adb shell getprop ro.product.model
adb shell getprop ro.build.display.id
adb shell getprop ro.product.manufacturer

# 2. ★ 最有用：列出所有 DJI 自启相关属性
adb shell getprop | Select-String "persist.dji"
#    重点 persist.dji.default_app —— 它的值就是自启的 App

# 3. 启动器是谁（注意可能被伪装，查 codePath 才知道真身）
adb shell cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.HOME
adb shell dumpsys package com.android.launcher3 | Select-String "codePath"
#    rc701 上显示 /product/priv-app/dpad_launcher —— DJI 定制启动器

# 4. 有哪些 DJI App
adb shell pm list packages | Select-String "dji"

# 5. 看"是谁、什么时候拉起的"
adb shell dumpsys activity recents | Select-String "mCallingPackage|baseIntent"
#    mCallingPackage 是启动器包名 => 确认是启动器开机拉起的（本机制适用）

# 6. 现场抓现行（重启后立刻看谁拉起它）
adb logcat -c
adb shell am force-stop <包名>
adb logcat -d | Select-String "<包名>|Start proc"
```

**如果第 2 步找不到 `persist.dji.*`**（非 DJI 设备，或机型机制不同），用通用兜底：
```powershell
adb shell pm disable-user --user 0 <包名>     # 直接禁用，也阻止自启
```

---

## 六、注意事项

- **不用 root**，普通 adb shell 即可（`setprop` + `pm disable-user` 均已实测）。
- 属性改成启动器包名后，开机会**停在桌面**，不会进任何 DJI App。
- **新机器先 `discover` 摸清楚再动手**，别直接套 rc701 的包名。
- ⚠️ `scripts/dji-rc/*.ps1` 是 **UTF-8 带 BOM**——Windows PowerShell 5.1 读无 BOM 的 `.ps1`
  会按 GBK 解码，含中文直接 ParserError。**改动后务必保持 BOM**。
- 脚本生成的 `dji-autostart.state` 记录原值，**别删**，`on` 依赖它恢复。
- **DJI 固件 OTA 后属性可能被重置**，重新执行一次 `off` 即可。

---

## 七、与本项目的关系

本项目的 App（`com.tunnathub.app`）部署在 DJI RC 上，**开机自启被 DJI 农业 App 抢占**时用本方法解除：

```powershell
# 取消 DJI 农业自启 -> 开机停桌面 -> 手动/自启动我们的 App
.\scripts\dji-rc\dji-autostart.ps1 off -Reboot
```

若需让**我们的 App 开机自启**，可反过来把属性指向我们：
```powershell
adb shell setprop persist.dji.default_app com.tunnathub.app
```
（`persist.` 属性重启不丢；但注意这与 DJI 官方 App 自启是同一个开关，二选一。）
