@echo off
chcp 65001 >nul

REM ================================================================================
REM VITA v15.1 停止服务脚本
REM ================================================================================

echo.
echo ================================================================================
echo VITA v15.1 停止服务
echo ================================================================================
echo.

REM 检查是否有运行的 Python 进程
tasklist | find /i "python.exe" >nul
if !errorlevel! neq 0 (
    echo ⚠️  未检测到运行中的 Python 进程
    echo.
    pause
    exit /b
)

echo 检测到运行中的 Python 进程:
tasklist | find /i "python.exe"
echo.

set /p choice=确认要停止所有 Python 进程吗? (Y/N):
if /i "%choice%" neq "Y" (
    echo 操作已取消
    exit /b
)

echo.
echo 正在停止服务...
taskkill /IM python.exe /F

echo.
echo ✅ 服务已停止
echo.
pause
