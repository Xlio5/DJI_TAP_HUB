#Requires -Version 5.1
<#
.SYNOPSIS
    DJI RC Plus 2(Agras 版, rc701)上 com.dji.agrasx 开机自启控制。

.DESCRIPTION
    该遥控器开机时会由 DJI 定制的启动器 dpad_launcher(对外包名 com.android.launcher3)
    读取系统属性 persist.dji.default_app, 自动拉起该属性指定的 App。
    出厂值 = com.dji.agrasx(农业 App), 所以一开机就直接进入农业界面。

    本脚本通过改写这个属性来取消自启(App 仍可手动点开);
    另外也提供 "彻底禁用 App" 和 "临时强停" 两种备选方式。

.PARAMETER Mode
    status         查看当前状态(默认)
    autostart-off  取消自启: persist.dji.default_app -> com.android.launcher3
    autostart-on   恢复自启: persist.dji.default_app -> com.dji.agrasx
    disable        彻底禁用 App(pm disable-user, 无法手动打开)
    enable         解除禁用
    kill           立即强停正在运行的农业 App(重启后仍会自启, 除非已 autostart-off)

.PARAMETER Reboot
    执行动作后重启遥控器并等待开机完成(用于验证效果)。

.EXAMPLE
    .\dji-agras.ps1 status
    .\dji-agras.ps1 autostart-off -Reboot
    .\dji-agras.ps1 autostart-on
    .\dji-agras.ps1 kill
#>
[CmdletBinding()]
param(
    [ValidateSet('status', 'autostart-off', 'autostart-on', 'disable', 'enable', 'kill')]
    [string]$Mode = 'status',

    [switch]$Reboot
)

$ErrorActionPreference = 'Stop'

$Pkg      = 'com.dji.agrasx'                # 农业 App
$Prop     = 'persist.dji.default_app'       # 决定开机自启哪个 App
$HomePkg  = 'com.android.launcher3'         # DJI 定制启动器 dpad_launcher
$BootCtrl = 'persist.dji.boot_apks_ctrl'    # 开机启动 App 总开关(1=开)

function Assert-Adb {
    if (-not (Get-Command adb -ErrorAction SilentlyContinue)) {
        throw 'adb 不在 PATH 中, 请先安装 Android Platform-Tools。'
    }
    $dev = (adb devices | Out-String)
    if ($dev -notmatch '\tdevice') {
        throw "没有可用的 adb 设备, 请确认 USB 已连接且已授权调试。`n$dev"
    }
}

function Get-Prop([string]$Name) {
    return (adb shell getprop $Name | Out-String).Trim()
}

function Set-And-VerifyProp([string]$Name, [string]$Value) {
    adb shell setprop $Name $Value | Out-Null
    $now = Get-Prop $Name
    if ($now -ne $Value) {
        throw "设置 $Name 失败: 期望 '$Value', 实际 '$now'"
    }
}

function Get-CurActivity {
    $line = adb shell dumpsys activity activities |
            Select-String -Pattern 'mResumedActivity' | Select-Object -First 1
    if ($line) { return $line.ToString().Trim() }
    return '(未知)'
}

function Show-Status {
    $dev  = ((adb devices | Where-Object { $_ -match '\tdevice' }) -join ' ').Trim()
    $user = adb shell dumpsys package $Pkg | Select-String -Pattern 'User 0: ceDataInode'
    $appPid = (adb shell pidof $Pkg | Out-String).Trim()

    Write-Host ''
    Write-Host '===== DJI Agras 自启状态 =====' -ForegroundColor Cyan
    Write-Host ("设备           : {0}" -f $dev)
    Write-Host ("App 包名       : {0}" -f $Pkg)
    Write-Host ("App 启用状态   : {0}" -f $user.ToString().Trim())
    Write-Host ("default_app    : {0}" -f (Get-Prop $Prop))
    Write-Host ("boot_apks_ctrl : {0}" -f (Get-Prop $BootCtrl))
    Write-Host ("前台 Activity  : {0}" -f (Get-CurActivity))
    if ($appPid) {
        Write-Host ("农业 App PID   : {0} (正在运行)" -f $appPid)
    } else {
        Write-Host  '农业 App PID   : (未运行)'
    }
    Write-Host ''
}

Assert-Adb

switch ($Mode) {
    'status' {
        Show-Status
    }
    'autostart-off' {
        Set-And-VerifyProp $Prop $HomePkg
        Write-Host ("已取消自启: {0} = {1}" -f $Prop, $HomePkg) -ForegroundColor Green
        Write-Host '开机将停在桌面; 农业 App 仍可手动打开。' -ForegroundColor Green
    }
    'autostart-on' {
        Set-And-VerifyProp $Prop $Pkg
        Write-Host ("已恢复自启: {0} = {1}" -f $Prop, $Pkg) -ForegroundColor Green
    }
    'disable' {
        adb shell pm disable-user --user 0 $Pkg
        Write-Host '已彻底禁用农业 App(无法手动打开)。恢复请执行: -Mode enable' -ForegroundColor Yellow
    }
    'enable' {
        adb shell pm enable $Pkg
        Write-Host '已解除禁用。' -ForegroundColor Green
    }
    'kill' {
        adb shell am force-stop $Pkg
        Write-Host '已强停农业 App(重启后仍会自启, 除非已执行 autostart-off)。' -ForegroundColor Green
    }
}

if ($Reboot -and $Mode -ne 'status') {
    # 重启阶段放宽错误处理: adb 在设备重新枚举时会往 stderr 写信息
    $ErrorActionPreference = 'Continue'
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
