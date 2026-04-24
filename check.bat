@echo off
chcp 65001 >nul

cd /d "%~dp0"

echo.
echo Running VITA environment check...
echo.

E:\vita\.venv\Scripts\python.exe check_env.py

echo.
pause
