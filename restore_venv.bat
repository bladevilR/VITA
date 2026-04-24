@echo off
chcp 65001 >nul

echo.
echo ========================================
echo VITA - Restore Virtual Environment
echo ========================================
echo.

cd /d E:\vita

if not exist ".venv_backup" (
    echo ERROR: No backup found
    pause
    exit /b 1
)

if exist ".venv" (
    echo Removing broken venv...
    rmdir /s /q ".venv"
)

echo Restoring old venv...
ren ".venv_backup" ".venv"

echo.
echo ========================================
echo Virtual environment restored!
echo ========================================
echo.
pause
