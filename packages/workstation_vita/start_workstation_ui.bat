@echo off
setlocal

set "ROOT=%~dp0"
cd /d "%ROOT%"
set "PYTHONPATH=%ROOT%vendor;%ROOT%src"
set "PYTHON_EXE=%ROOT%runtime\python\python.exe"
set "UI_PORT=8501"

if not exist "%PYTHON_EXE%" if exist "D:\miniconda3\python.exe" set "PYTHON_EXE=D:\miniconda3\python.exe"
if not exist "%PYTHON_EXE%" set "PYTHON_EXE=python"

if not exist "%ROOT%.env" (
    echo [ERROR] Missing .env file: %ROOT%
    pause
    exit /b 1
)

if not exist "%ROOT%kb_zhipu.index" (
    echo [ERROR] Missing kb_zhipu.index: %ROOT%
    pause
    exit /b 1
)

if not exist "%ROOT%kb_zhipu_id_map.npy" (
    echo [ERROR] Missing kb_zhipu_id_map.npy: %ROOT%
    pause
    exit /b 1
)

title VITA Workstation UI
"%PYTHON_EXE%" -X utf8 -m streamlit run "%ROOT%src\workstation_vita\ui_app.py" --global.developmentMode false --server.port %UI_PORT% --server.address 0.0.0.0 --server.headless true --browser.gatherUsageStats false
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
    echo.
    echo [ERROR] UI startup failed with exit code %EXIT_CODE%.
    pause
)

endlocal
