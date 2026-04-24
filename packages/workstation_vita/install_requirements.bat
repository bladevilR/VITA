@echo off
setlocal

set ROOT=%~dp0
cd /d "%ROOT%"
echo 本包已经内置 vendor\ 依赖和 runtime\python 运行时。
echo 无需联网安装任何依赖，直接启动即可。
echo.
pause

endlocal
