@echo off
setlocal
powershell.exe -ExecutionPolicy Bypass -File "%~dp0stop_bridge.ps1"
