@echo off
setlocal

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_release.ps1"
set EXIT_CODE=%ERRORLEVEL%

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [错误] 发布包生成失败，退出码 %EXIT_CODE%。
    pause
    exit /b %EXIT_CODE%
)

echo.
echo [完成] 发布包已生成。
pause

endlocal
