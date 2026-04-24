@echo off
setlocal

set "ROOT=%~dp0"
cd /d "%ROOT%"
set "PYTHONPATH=%ROOT%vendor;%ROOT%src"
set "PYTHON_EXE=%ROOT%runtime\python\python.exe"

if not exist "%PYTHON_EXE%" if exist "D:\miniconda3\python.exe" set "PYTHON_EXE=D:\miniconda3\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

if not exist "%ROOT%.env" (
    echo [ERROR] Missing .env file: %ROOT%
    pause
    exit /b 1
)

title VITA Server API
"%PYTHON_EXE%" -X utf8 -m server_maximo.app
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [ERROR] Server startup failed with exit code %EXIT_CODE%.
    pause
)

endlocal
