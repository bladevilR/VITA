@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul

echo.
echo Searching for Python in your system...
echo This may take a moment...
echo.

REM Search on C:\ drive
dir /s /b C:\python.exe 2>nul

REM Search on D:\ drive if it exists
if exist D:\ (
    dir /s /b D:\python.exe 2>nul
)

REM Search on E:\ drive if it exists
if exist E:\ (
    dir /s /b E:\python.exe 2>nul
)

echo.
echo.
echo Please copy the path above and tell me where python.exe is located
echo For example: C:\Users\R\AppData\Local\Programs\Python\Python39\python.exe
echo.
pause
