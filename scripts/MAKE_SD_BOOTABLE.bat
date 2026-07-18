@echo off
REM ============================================================
REM  MAKE SD CARD BOOTABLE FOR V3s
REM  Writes SPL+U-Boot to sector 8 of SD card
REM  MUST run as Administrator!
REM ============================================================
echo ============================================================
echo   MAKE SD CARD BOOTABLE FOR V3s
echo   Target: \\.\PhysicalDrive2
echo ============================================================
echo.

python -B "c:\my_project\TUN_NAT_HUB\scripts\make_sd_bootable.py"
if %errorlevel% neq 0 (
    echo.
    echo FAILED! Press any key...
    pause
    exit /b 1
)
echo.
pause
