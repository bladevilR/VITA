@echo off
setlocal

set ROOT=%~dp0
cd /d "%ROOT%"
set PYTHONPATH=%ROOT%vendor;%ROOT%src
set PYTHON_EXE=%ROOT%runtime\python\python.exe

if not exist "%PYTHON_EXE%" if exist "D:\miniconda3\python.exe" set PYTHON_EXE=D:\miniconda3\python.exe
if not exist "%PYTHON_EXE%" set PYTHON_EXE=python

if not exist "%ROOT%.env" (
    echo [错误] 未找到 .env 文件：%ROOT%
    echo 请保持整个服务端包完整，不要单独拷贝脚本。
    echo.
    pause
    exit /b 1
)

title VITA 服务端接口
"%PYTHON_EXE%" -X utf8 -m server_maximo.app
set EXIT_CODE=%ERRORLEVEL%

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [错误] 服务端接口启动失败，退出码 %EXIT_CODE%。
    pause
)

endlocal
