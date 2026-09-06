param(
    [string]$Serial = "",
    [int]$Duration = 0,
    [switch]$Raw,
    [switch]$Hex,
    [string]$AdbHost = "127.0.0.1",
    [int]$AdbPort = 40007
)

$ErrorActionPreference = "Stop"

function Resolve-RepoRoot {
    $scriptDir = Split-Path -Parent $PSCommandPath
    return (Resolve-Path (Join-Path $scriptDir "..")).Path
}

function Get-AdbCommand {
    $adb = Get-Command adb -ErrorAction SilentlyContinue
    if (-not $adb) {
        throw "adb not found. Please add Android platform-tools to PATH."
    }
    return $adb.Source
}

function Get-AdbSerial {
    param(
        [string]$Adb,
        [string]$RequestedSerial
    )

    if ($RequestedSerial) {
        return $RequestedSerial
    }

    $lines = & $Adb devices
    $devices = @()
    foreach ($line in $lines) {
        if ($line -match "^(\S+)\s+device$") {
            $devices += $Matches[1]
        }
    }

    if ($devices.Count -eq 0) {
        throw "No authorized adb device found."
    }
    if ($devices.Count -gt 1) {
        Write-Host "Multiple adb devices found. Re-run with -Serial:" -ForegroundColor Yellow
        foreach ($device in $devices) {
            Write-Host "  $device"
        }
        throw "Multiple devices, but -Serial was not specified."
    }
    return $devices[0]
}

function Get-Timestamp {
    return Get-Date -Format "yyyyMMdd_HHmmss"
}

$repoRoot = Resolve-RepoRoot
$adb = Get-AdbCommand
$serialArg = Get-AdbSerial -Adb $adb -RequestedSerial $Serial
$monitor = Join-Path $repoRoot "scripts\rc_40007_serial_monitor.py"
$tmpDir = Join-Path $repoRoot "tmp"

if (-not (Test-Path -LiteralPath $monitor)) {
    throw "Monitor script not found: $monitor"
}

if (-not (Test-Path -LiteralPath $tmpDir)) {
    New-Item -ItemType Directory -Path $tmpDir | Out-Null
}

Write-Host "40007 ADB monitor" -ForegroundColor Cyan
Write-Host "ADB device : $serialArg"
Write-Host "Target     : $AdbHost`:$AdbPort"

if ($Raw) {
    $stamp = Get-Timestamp
    $outFile = Join-Path $tmpDir "p40007_capture_$stamp.bin"
    $remotePrefix = ""
    if ($Duration -gt 0) {
        $remotePrefix = "timeout $Duration "
    }

    Write-Host "Mode       : raw capture"
    Write-Host "Output     : $outFile"
    Write-Host "Tip        : Move sticks or press buttons. Ctrl+C stops capture."

    $cmdLine = "`"$adb`" -s `"$serialArg`" exec-out $remotePrefix`"toybox`" `"nc`" `"$AdbHost`" `"$AdbPort`" > `"$outFile`""
    cmd.exe /d /c $cmdLine
    if ($LASTEXITCODE -ne 0) {
        throw "adb raw capture failed rc=$LASTEXITCODE"
    }

    $size = (Get-Item -LiteralPath $outFile).Length
    Write-Host "Done       : $size bytes"
    if ($size -gt 0) {
        Write-Host "Preview    :"
        Format-Hex -Path $outFile -Count 256
    }
    exit 0
}

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    $python = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $python) {
    throw "python/py not found, cannot run the 40007 parser."
}

$argsList = @(
    $monitor,
    "--adb", $serialArg,
    "--adb-host", $AdbHost,
    "--adb-port", "$AdbPort"
)
if ($Duration -gt 0) {
    $argsList += @("--duration", "$Duration")
}
if ($Hex) {
    $argsList += "--hex"
}

Write-Host "Mode       : decoded RC output"
Write-Host "Tip        : Move sticks or press buttons. Ctrl+C stops monitor."
Write-Host ""

& $python.Source @argsList
