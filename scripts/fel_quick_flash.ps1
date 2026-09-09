param(
    [switch]$FullSpi,
    [switch]$SkipBuild,
    [switch]$DryRun,
    [string]$Version = "",
    [string]$Distro = "Ubuntu-20.04",
    [string]$ProjectWsl = "/mnt/c/my_project/TUN_NAT_HUB",
    [string]$FelVidPid = "1f3a:efe8"
)

$ErrorActionPreference = "Stop"

function Step($Message) {
    $now = Get-Date -Format "HH:mm:ss"
    Write-Host "[$now] $Message"
}

function Run($Exe, [string[]]$ArgsList) {
    Step ("run: " + $Exe + " " + ($ArgsList -join " "))
    if ($DryRun) { return }
    & $Exe @ArgsList
    if ($LASTEXITCODE -ne 0) {
        throw "$Exe failed with exit code $LASTEXITCODE"
    }
}

function Wsl([string]$Command) {
    Run "wsl.exe" @("-d", $Distro, "--", "bash", "-lc", $Command)
}

function Sha256File([string]$Path) {
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash
}

function Next-Version {
    $backup = Join-Path $PSScriptRoot "..\backup"
    $max = 0
    Get-ChildItem -LiteralPath $backup -Recurse -ErrorAction SilentlyContinue |
        ForEach-Object {
            if ($_.Name -match "v1\.6\.(\d+)") {
                $n = [int]$Matches[1]
                if ($n -gt $max) { $max = $n }
            }
        }
    if ($max -lt 1) { return "v1.6.1" }
    return "v1.6.$($max + 1)"
}

function Ensure-Wsl-Alive {
    Step "keep WSL alive"
    Start-Process -WindowStyle Hidden -FilePath "wsl.exe" -ArgumentList @("-d", $Distro, "--", "sleep", "900") | Out-Null
    Start-Sleep -Seconds 1
}

function Get-FelBusId {
    $list = & usbipd list
    $line = $list | Where-Object { $_ -match $FelVidPid } | Select-Object -First 1
    if (-not $line) {
        throw "FEL device $FelVidPid not found. Put the board into FEL and reconnect USB."
    }
    if ($line -match "^\s*(\S+)\s+$FelVidPid\s+") {
        return $Matches[1]
    }
    throw "FEL device found but BUSID parse failed: $line"
}

function Ensure-Fel-Attached {
    Step "check Windows USB FEL device"
    $busId = Get-FelBusId
    Step "FEL BUSID: $busId"
    $stateLine = (& usbipd list | Where-Object { $_ -match "^\s*$([regex]::Escape($busId))\s+" } | Select-Object -First 1)
    if ($stateLine -match "Attached") {
        Step "FEL already attached to WSL"
        return
    }
    Step "attach FEL to WSL"
    Run "usbipd" @("attach", "--wsl", $Distro, "--busid", $busId)
}

function Ensure-SunxiFel-Sees-Device {
    Step "check sunxi-fel"
    Wsl "sunxi-fel list | grep -q 'Allwinner V3s'"
    Wsl "sunxi-fel list"
}

function Build-Artifacts {
    if ($SkipBuild) {
        Step "skip build by request"
        return
    }
    Step "build rootfs and SPI image"
    Wsl "cd '$ProjectWsl' && bash scripts/build_rootfs_only_current.sh && python3 -B scripts/build_spi_final.py"
}

function Archive-Artifacts {
    param([string]$Version, [string]$Timestamp)
    $root = Resolve-Path (Join-Path $PSScriptRoot "..")
    $backup = Join-Path $root "backup"
    $release = Join-Path $backup "release_${Timestamp}_${Version}_fel"
    New-Item -ItemType Directory -Path $release -Force | Out-Null

    $rootfs = Join-Path $backup "rootfs.squashfs"
    $spi = Join-Path $backup "spi_image.bin"
    $rootfsOut = Join-Path $release "rootfs_${Version}_${Timestamp}.squashfs"
    $spiOut = Join-Path $release "spi_image_${Version}_${Timestamp}.bin"
    Copy-Item -LiteralPath $rootfs -Destination $rootfsOut
    Copy-Item -LiteralPath $spi -Destination $spiOut

    $commit = (& git -c safe.directory=C:/my_project/TUN_NAT_HUB rev-parse --short HEAD).Trim()
    $branch = (& git -c safe.directory=C:/my_project/TUN_NAT_HUB rev-parse --abbrev-ref HEAD).Trim()
    $mode = if ($FullSpi) { "full-spi" } else { "rootfs-only" }
    $manifest = Join-Path $release "manifest.md"
    $lines = @(
        "# TUN_NAT_HUB FEL Release",
        "",
        "version: $Version",
        "timestamp: $Timestamp",
        "commit: $commit",
        "branch: $branch",
        "flash_mode: $mode",
        "",
        "## Files"
    )
    foreach ($file in @($rootfsOut, $spiOut)) {
        $item = Get-Item -LiteralPath $file
        $lines += "- $($item.Name)"
        $lines += "  size: $($item.Length)"
        $lines += "  sha256: $(Sha256File $file)"
    }
    Set-Content -LiteralPath $manifest -Value ($lines -join "`n") -Encoding UTF8

    if ((Sha256File $rootfs) -ne (Sha256File $rootfsOut)) { throw "Hash mismatch after rootfs archive copy" }
    if ((Sha256File $spi) -ne (Sha256File $spiOut)) { throw "Hash mismatch after SPI archive copy" }

    Step "release: $release"
    return @{
        Dir = $release
        Rootfs = $rootfsOut
        Spi = $spiOut
        Manifest = $manifest
    }
}

function Flash-RootfsOnly {
    param([string]$Rootfs)
    $rootfsWsl = $Rootfs -replace "\\", "/"
    $rootfsWsl = $rootfsWsl -replace "^C:", "/mnt/c"
    $size = (Get-Item -LiteralPath $Rootfs).Length
    if ($size -gt 4685824) {
        throw "rootfs too large for 4576KB partition: $size"
    }
    Step "rootfs-only FEL flash: 0x710000, $size bytes"
    if ($DryRun) {
        Step "dry run: skip spiflash-write 0x710000 and spiflash-read readback_rootfs"
        return
    }
    Wsl "sunxi-fel spiflash-write 0x710000 '$rootfsWsl'"
    Wsl "rm -f /tmp/readback_rootfs.squashfs && sunxi-fel spiflash-read 0x710000 $size /tmp/readback_rootfs.squashfs"
    $expected = Sha256File $Rootfs
    $actual = (& wsl.exe -d $Distro -- bash -lc "sha256sum /tmp/readback_rootfs.squashfs | awk '{print `$1}'").Trim().ToUpperInvariant()
    Step "rootfs expected sha256: $expected"
    Step "rootfs readback sha256: $actual"
    if ($expected -ne $actual) { throw "Hash mismatch after rootfs readback" }
}

function Flash-FullSpi {
    param([string]$Spi)
    $spiWsl = $Spi -replace "\\", "/"
    $spiWsl = $spiWsl -replace "^C:", "/mnt/c"
    $size = (Get-Item -LiteralPath $Spi).Length
    if ($size -ne 16777216) {
        throw "SPI image must be exactly 16MB: $size"
    }
    Step "full SPI FEL flash: 16MB"
    if ($DryRun) {
        Step "dry run: skip spiflash-write 0 and spiflash-read readback_spi"
        return
    }
    Wsl "sunxi-fel spiflash-write 0 '$spiWsl'"
    Wsl "rm -f /tmp/readback_spi.bin && sunxi-fel spiflash-read 0 16777216 /tmp/readback_spi.bin"
    $expected = Sha256File $Spi
    $actual = (& wsl.exe -d $Distro -- bash -lc "sha256sum /tmp/readback_spi.bin | awk '{print `$1}'").Trim().ToUpperInvariant()
    Step "spi expected sha256: $expected"
    Step "spi readback sha256: $actual"
    if ($expected -ne $actual) { throw "Hash mismatch after full SPI readback" }
}

if ([string]::IsNullOrWhiteSpace($Version)) {
    $Version = Next-Version
}
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$modeText = if ($FullSpi) { "full-spi" } else { "rootfs-only" }
Step "TUN_NAT_HUB FEL quick flash: $Version, $modeText"
if ($DryRun) { Step "dry run enabled: commands are printed but not executed" }

Ensure-Wsl-Alive
Ensure-Fel-Attached
Ensure-SunxiFel-Sees-Device
Build-Artifacts
$artifacts = Archive-Artifacts -Version $Version -Timestamp $Timestamp

if ($FullSpi) {
    Flash-FullSpi -Spi $artifacts.Spi
} else {
    Flash-RootfsOnly -Rootfs $artifacts.Rootfs
}

Step "FEL flash verified: $($artifacts.Dir)"
