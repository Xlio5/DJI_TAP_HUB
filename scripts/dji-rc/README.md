# DJI 遥控器 —— 取消开机自动拉起某个 App

适用:DJI RC / RC Plus / RC Plus 2 / RC Pro / RC2 / Smart Controller 等**安卓底层的 DJI 遥控器**,
通过 USB + adb 调试。

已验证机型:DJI RC PLUS 2(rc701,农业版固件 V01.29.00.07,Android 11)—— 关掉了 `com.dji.agrasx` 的开机自启。

---

## 一、原理

DJI 遥控器固件里,**开机自动拉起哪个 App 是由一个系统属性决定的**:

```
persist.dji.default_app = <包名>
```

DJI 定制的启动器(在 rc701 上对外包名伪装成 `com.android.launcher3`,实际来自
`/product/priv-app/dpad_launcher`)在开机时读这个属性,然后拉起对应的 App。

于是:

| 目标 | 做法 |
|---|---|
| 取消自启,保留 App 手动可用 | 把属性改成一个不打扰你的 App —— 通常就改成**启动器自己** |
| 恢复原样 | 把属性写回原值 |
| 属性不可写 / 想彻底关 | 直接 `pm disable-user` 禁用该 App(兜底) |

两个关键点:

1. **这个属性的值就是那个自启 App 的包名** —— 所以在任何机器上都不用猜。
2. `persist.` 前缀的属性写在 `/data/property`,**重启不丢**,一次设置长期有效。

> ⚠️ 唯一会失效的情况:DJI 固件 OTA 升级后属性可能被覆盖回原值,重新设一次即可。

---

## 二、快速使用(脚本)

`dji-autostart.ps1` —— 不写死包名,自动从 `persist.dji.default_app` 读取目标 App,可直接搬到其他 DJI 遥控器用。

```powershell
# 0) 通用排查:先看看这台机器的机制 (强烈建议新机器先跑这个)
.\dji-autostart.ps1 discover

# 1) 查看当前状态
.\dji-autostart.ps1 status

# 2) 取消自启(原值会存到 dji-autostart.state,方便恢复)
.\dji-autostart.ps1 off -Reboot

# 3) 恢复自启
.\dji-autostart.ps1 on

# 4) 兜底:彻底禁用 / 解除禁用 / 临时强停
.\dji-autostart.ps1 disable
.\dji-autostart.ps1 enable
.\dji-autostart.ps1 kill
```

其他机型/其他 DJI App(脚本没猜到时用 `-Package` 指定):

```powershell
.\dji-autostart.ps1 off -Package com.dji.industry.pilot   # DJI Pilot 2
.\dji-autostart.ps1 off -Package dji.go.v5                # DJI Fly
.\dji-autostart.ps1 off -Package com.dji.agrasx           # Agras 农业
```

---

## 三、手动命令(不用脚本)

```powershell
# 看自启的是谁
adb shell getprop persist.dji.default_app

# 看启动器是谁(作为安全的替代值)
adb shell cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.HOME

# 取消自启(把值改成启动器包名),然后重启
adb shell setprop persist.dji.default_app com.android.launcher3
adb reboot

# 恢复(写回原包名)
adb shell setprop persist.dji.default_app com.dji.agrasx

# 兜底:彻底禁用 / 恢复(不需要 root)
adb shell pm disable-user --user 0 com.dji.agrasx
adb shell pm enable com.dji.agrasx

# 临时关掉当前实例(重启后仍会自启)
adb shell am force-stop com.dji.agrasx
```

---

## 四、换一台新机器,怎么自己排查

按顺序跑,基本 5 分钟能定位:

```powershell
# 1. 是不是 DJI 遥控器 + 安卓版本
adb shell getprop ro.product.model
adb shell getprop ro.build.display.id
adb shell getprop ro.product.manufacturer

# 2. ★ 最有用的一步:把 DJI 的自启相关属性全列出来
adb shell getprop | Select-String "persist.dji"
#    重点看 persist.dji.default_app —— 它的值就是自启的 App

# 3. 启动器是谁(注意可能被伪装,查 codePath 才知道真身)
adb shell cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.HOME
adb shell dumpsys package com.android.launcher3 | Select-String "codePath"
#    rc701 上会显示 /product/priv-app/dpad_launcher —— 说明是 DJI 定制的启动器

# 4. 有哪些 DJI App
adb shell pm list packages | Select-String "dji"

# 5. 出问题时看"是谁、在什么时候拉起的"
adb shell dumpsys activity recents | Select-String "mCallingPackage|baseIntent"
#    mCallingPackage 是启动器包名 => 确认是启动器在开机时拉起的

# 6. 想现场抓现行(重启后立刻看谁拉起它)
adb logcat -c
adb shell am force-stop <包名>
adb logcat -d | Select-String "<包名>|Start proc"
```

**如果第 2 步找不到 `persist.dji.*` 属性**(非 DJI 设备,或机型机制不同),就用通用兜底:

```powershell
adb shell pm disable-user --user 0 <包名>     # 直接禁用,也会阻止自启
```

---

## 五、注意事项

- **不用 root**,普通 adb shell 权限即可(`setprop` 和 `pm disable-user` 都验证过)。
- `persist.dji.default_app` 改成启动器包名后,开机会**停在桌面**,不会进任何 DJI App。
- 建议新机器先 `-Mode discover` 摸清楚再动手,别直接套 rc701 的包名。
- 本目录的 `.ps1` 都是 **UTF-8 带 BOM** —— Windows PowerShell 5.1 读无 BOM 的 `.ps1` 会按 GBK 解码,
  含中文时直接报 ParserError。改动脚本后记得保持 BOM。
- 脚本会生成 `dji-autostart.state` 记录原值,别删,`on` 要靠它恢复。
