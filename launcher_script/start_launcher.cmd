@echo off
setlocal

cd /d "%~dp0"

powershell.exe ^
    -NoLogo ^
    -NoProfile ^
    -ExecutionPolicy Bypass ^
    -File "%~dp0start-stack.ps1"

if errorlevel 1 (
    echo.
    echo The stack launcher encountered an error.
    pause
)