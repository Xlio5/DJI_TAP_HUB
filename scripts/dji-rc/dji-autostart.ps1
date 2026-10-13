#Requires -Version 5.1
<#
.SYNOPSIS
    DJI 遥控器(RC / RC Plus / RC Pro / RC2 / Smart Controller 等)
    —— 取消指定 App 的开机自动拉起, 可迁移到其他机器。

.DESCRIPTION
    原理: DJI 遥控器固件中, 开机自启的 App 由系统属性 persist.dji.default_app 决定。
    DJI 定制的启动器(部分机型伪装成包名 com.android.launcher3, 实际来自
    /product/priv-app/dpad_launcher)开机读取该属性, 并拉起对应 App。

    所以:
      取消自启 = 把 persist.dji.default_app 改成一个不打扰你的 App(通常就是启动器自己);
      App 保持安装、可手动打开;想恢复就把属性写回原值。

    本脚本不写死任何包名 —— 目标 App 直接从 persist.dji.default_app 读取,
    因此在其他 DJI 机型/其他 DJI App(DJI Pilot 2 / DJI Fly / Agras 等)上同样可用。

    若目标机器上没有 persist.dji.* 属性(非 DJI 设备或机制不同),
    请先跑 -Mode discover 走通用排查流程, 或直接用 -Mode disable 兜底。

.PARAMETER Mode
    status    查看当前状态(默认)
    discover  通用排查: 设备信息 / 启动器 / DJI 包 / persist.dji.* 属性 / 最近任务发起者
    off       取消自启(原值存入 dji-autostart.state, 属性改为启动器包名)
    on        恢复自启(从 state 文件恢复, 或用 -Package 指定)
    disable   彻底禁用该 App(pm disable-user, 无法手动打开 —— 兜底方案)
    enable    解除禁用
    kill      立即强停该 App(重启后若未 off 仍会自启)

.PARAMETER Package
    指定目标 App 包名。默认自动取 persist.dji.default_app 的值。
    常见值: com.dji.agrasx(农业) / com.dji.industry.pilot(DJI Pilot 2) / dji.go.v5(DJI Fly)

.PARAMETER Reboot
    动作执行后重启遥控器并等待开机完成(用于验证效果)。

.EXAMPLE
    .\dji-autostart.ps1 discover
    .\dji-autostart.ps1 off -Reboot
    .\dji-autostart.ps1 status
    .\dji-autostart.ps1 on
    .\dji-autostart.ps1 disable -Package com.dji.industry.pilot
#>
[CmdletBinding()]
param(
    [ValidateSet('status', 'discover', 'off', 'on', 'disable', 'enable', 'kill')]
    [string]$Mode = 'status',

    [string]$Package,

    [switch]$Reboot
)

$ErrorActionPreference = 'Stop'

$Prop      = 'persist.dji.default_app'
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$StateFile = Join-Path $ScriptDir 'dji-autostart.state'

# ------------------------------------------------------------------ 基础函数

function Assert-Adb {
    if (-not (Get-Command adb -ErrorAction SilentlyContinue)) {
        throw 'adb 不在 PATH 中, 请先安装 Android Platform-Tools 并加入 PATH。'
    }
    $dev = (adb devices | Out-String)
    if ($dev -notmatch '\tdevice') {
        throw "没有可用的 adb 设备, 请确认 USB 已连接且已授权 USB 调试。`n$dev"
    }
}

function Get-Prop([string]$Name) {
    return (adb shell getprop $Name | Out-String).Trim()
}

function Set-And-VerifyProp([string]$Name, [string]$Value) {
    adb shell setprop $Name $Value | Out-Null
    $now = Get-Prop $Name
    if ($now -ne $Value) {
        throw "设置 $Name 失败: 期望 '$Value', 实际 '$now'。(某些机型该属性只读, 请改用 -Mode disable)"
    }
}

function Get-HomePackage {
    $out = adb shell cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.HOME | Out-String
    foreach ($line in ($out -split "`r?`n")) {
        if ($line -match '/') { return $line.Split('/')[0].Trim() }
    }
    return 'com.android.launcher3'
}

function Get-DjiPackages {
    $out  = adb shell pm list packages | Out-String
    $list = @()
    foreach ($line in ($out -split "`r?`n")) {
        if ($line -match '^package:(.*dji.*)$') { $list += $Matches[1].Trim() }
    }
    return $list
}

function Get-AutoApp {
    if ($Package) { return $Package }
    $v = Get-Prop $Prop
    # 执行过 off 后, 属性被改成了启动器; 真正的目标 App 记录在 state 文件里
    if ($v -and (Test-Path $StateFile)) {
        if ($v -eq (Get-HomePackage)) {
            $saved = (Get-Content $StateFile -Raw).Trim().TrimStart([char]0xFEFF)
            if ($saved) { return $saved }
        }
    }
    if ($v) { return $v }
    return $null
}

function Get-CurActivity {
    $l = adb shell dumpsys activity activities | Select-String -Pattern 'mResumedActivity' | Select-Object -First 1
    if ($l) { return $l.ToString().Trim() }
    return '(未知)'
}

function Test-IsDji {
    return ((adb shell getprop | Out-String) -match 'persist\.dji\.' -or
            (Get-Prop 'ro.product.manufacturer') -eq 'DJI')
}

# ------------------------------------------------------------------ 展示

function Show-Status {
    $app     = Get-AutoApp
    $propVal = Get-Prop $Prop
    $homePkg = Get-HomePackage

    Write-Host ''
    Write-Host '===== DJI 自启状态 =====' -ForegroundColor Cyan
    Write-Host ("设备            : {0}" -f (Get-Prop 'ro.product.model'))
    Write-Host ("目标 App        : {0}" -f ($(if ($app) { $app } else { '(未知, 请跑 discover)' })))
    if ($app) {
        $st     = adb shell dumpsys package $app | Select-String -Pattern 'User 0: ceDataInode'
        $appPid = (adb shell pidof $app | Out-String).Trim()
        Write-Host ("App 启用状态    : {0}" -f ($(if ($st) { $st.ToString().Trim() } else { '(未安装?)' })))
        Write-Host ("App 进程        : {0}" -f ($(if ($appPid) { "$appPid (运行中)" } else { '(未运行)' })))
    }
    if ($propVal -eq $homePkg) {
        Write-Host  '自启状态        : 已关闭(开机停在桌面)' -ForegroundColor Green
    } else {
        Write-Host  '自启状态        : 开启(开机会自动拉起目标 App)' -ForegroundColor Yellow
    }
    Write-Host ("{0} : {1}" -f $Prop, $propVal)
    Write-Host ("启动器 (HOME)   : {0}" -f $homePkg)
    Write-Host ("开机启动总开关  : persist.dji.boot_apks_ctrl = {0}" -f (Get-Prop 'persist.dji.boot_apks_ctrl'))
    Write-Host ("前台 Activity   : {0}" -f (Get-CurActivity))
    Write-Host ''
}

function Show-Discover {
    Write-Host ''
    Write-Host '===== 通用排查 =====' -ForegroundColor Cyan
    Write-Host "--- 设备 ---"
    Write-Host ("model  : {0}" -f (Get-Prop 'ro.product.model'))
    Write-Host ("build  : {0}" -f (Get-Prop 'ro.build.display.id'))
    Write-Host ("brand  : {0}" -f (Get-Prop 'ro.product.manufacturer'))
    Write-Host ''
    Write-Host "--- 启动器 (HOME) ---"
    Write-Host ("HOME 包名 : {0}" -f (Get-HomePackage))
    adb shell cmd package resolve-activity --brief -a android.intent.action.MAIN -c android.intent.category.HOME
    Write-Host ''
    Write-Host "--- DJI 相关包 ---"
    $pkgs = Get-DjiPackages
    if ($pkgs.Count -eq 0) { Write-Host '  (无)' } else { $pkgs | ForEach-Object { Write-Host ("  {0}" -f $_) } }
    Write-Host ''
    Write-Host "--- persist.dji.* 属性 ---"
    $p = adb shell getprop | Select-String -Pattern 'persist\.dji\.'
    if ($p) { $p | ForEach-Object { Write-Host ("  {0}" -f $_.ToString().Trim()) } } else { Write-Host '  (无 —— 该机型可能机制不同)' }
    Write-Host ''
    Write-Host "--- 最近任务的发起者 (谁拉起了它) ---"
    adb shell dumpsys activity recents | Select-String -Pattern 'mCallingPackage|baseIntent' | Select-Object -First 8 | ForEach-Object { Write-Host ("  {0}" -f $_.ToString().Trim()) }
    Write-Host ''
    Write-Host '提示: mCallingPackage 若是启动器包名, 说明是启动器在开机时拉起的(即本脚本适用的机制)。' -ForegroundColor DarkGray
    Write-Host ''
}

# ------------------------------------------------------------------ 主流程

Assert-Adb
if (-not (Test-IsDji)) {
    Write-Warning '这台设备看起来不是 DJI 遥控器 —— 仍可尝试, 但机制可能不同。'
}

switch ($Mode) {

    'status' { Show-Status }

    'discover' { Show-Discover }

    'off' {
        $app = Get-AutoApp
        if (-not $app) {
            throw "无法确定自启 App。请先用 -Package <包名> 指定, 或跑 -Mode discover 排查。"
        }
        $homePkg = Get-HomePackage
        if ($app -eq $homePkg) {
            Write-Host ("属性已经是启动器 ({0}), 无需修改。" -f $homePkg) -ForegroundColor Yellow
            break
        }
        [System.IO.File]::WriteAllText($StateFile, $app, (New-Object System.Text.UTF8Encoding($false)))
        Set-And-VerifyProp $Prop $homePkg
        Write-Host ("已取消自启: {0}" -f $Prop) -ForegroundColor Green
        Write-Host ("  原值 {0} -> {1}" -f $app, $homePkg) -ForegroundColor Green
        Write-Host ("  原值已记录到 {0}, 用 -Mode on 可恢复。" -f $StateFile) -ForegroundColor Green
        Write-Host  '  需重启生效: 加 -Reboot, 或手动重启遥控器。' -ForegroundColor Green
    }

    'on' {
        $orig = $null
        if (Test-Path $StateFile) { $orig = (Get-Content $StateFile -Raw).Trim().TrimStart([char]0xFEFF) }
        if (-not $orig) { $orig = $Package }
        if (-not $orig) {
            throw "不知道要恢复成哪个 App。请用 -Package 指定, 例如:`n  -Package com.dji.agrasx`n  -Package com.dji.industry.pilot`n  -Package dji.go.v5"
        }
        Set-And-VerifyProp $Prop $orig
        Write-Host ("已恢复自启: {0} = {1}" -f $Prop, $orig) -ForegroundColor Green
        Write-Host '需重启生效。' -ForegroundColor Green
    }

    'disable' {
        $app = Get-AutoApp
        if (-not $app) { throw '请用 -Package <包名> 指定要禁用的 App。' }
        adb shell pm disable-user --user 0 $app
        Write-Host ("已彻底禁用 {0}。" -f $app) -ForegroundColor Yellow
        Write-Host ("恢复: .\dji-autostart.ps1 enable -Package {0}" -f $app) -ForegroundColor Yellow
    }

    'enable' {
        $app = Get-AutoApp
        if (-not $app) { throw '请用 -Package <包名> 指定要解除禁用的 App。' }
        adb shell pm enable $app
        Write-Host ("已解除禁用 {0}。" -f $app) -ForegroundColor Green
    }

    'kill' {
        $app = Get-AutoApp
        if (-not $app) { throw '请用 -Package <包名> 指定要强停的 App。' }
        adb shell am force-stop $app
        Write-Host ("已强停 {0}。" -f $app) -ForegroundColor Green
    }
}

# ------------------------------------------------------------------ 可选重启

if ($Reboot -and $Mode -in @('off', 'on', 'disable', 'enable')) {
    $ErrorActionPreference = 'Continue'   # adb 在设备重新枚举时会写 stderr
    Write-Host ''
    Write-Host '正在重启遥控器并等待开机...' -ForegroundColor Cyan
    adb reboot
    Start-Sleep -Seconds 5
    adb wait-for-device
    $tries = 0
    while ($tries -lt 60) {
        Start-Sleep -Seconds 3
        if ((Get-Prop 'sys.boot_completed') -eq '1') { break }
        $tries++
    }
    Start-Sleep -Seconds 8
    Write-Host '重启完成。' -ForegroundColor Green
    Show-Status
}
