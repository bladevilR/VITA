@echo off
chcp 65001 >nul

echo.
echo ========================================
echo VITA - Rebuild Virtual Environment
echo ========================================
echo.

cd /d E:\vita

REM Backup old venv
if exist ".venv_backup" (
    echo Removing old backup...
    rmdir /s /q ".venv_backup"
)

if exist ".venv" (
    echo Backing up old venv...
    ren ".venv" ".venv_backup"
)

echo.
echo Creating new virtual environment...
echo This may take 2-3 minutes...
echo.

D:\python3.13.2\python.exe -m venv .venv

if errorlevel 1 (
    echo ERROR: Failed to create virtual environment
    echo Restoring old venv...
    if exist ".venv_backup" (
        ren ".venv_backup" ".venv"
    )
    pause
    exit /b 1
)

echo.
echo Installing required packages...
echo.

.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel

.venv\Scripts\pip.exe install streamlit pandas numpy faiss-cpu requests oracledb

echo.
echo ========================================
echo Virtual environment rebuilt successfully
echo ========================================
echo.
echo Now you can run: start_vita.bat
echo.
pause
