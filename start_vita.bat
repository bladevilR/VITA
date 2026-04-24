@echo off
chcp 65001 >nul

REM 关闭 QuickEdit 模式，防止点击终端窗口导致进程暂停
reg add "HKCU\Console" /v QuickEdit /t REG_DWORD /d 0 /f >nul 2>&1

cd /d E:\vita

REM 设置数据库环境变量
set VITA_DB_USER=maxsearch
set VITA_DB_PASSWORD=sZ36!mTrBxH
set VITA_DB_DSN=htdora-scan.sz-mtr.com:1521/eamprod

REM 设置LLM环境变量（主：GLM-4.7 新地址）
set VITA_LLM_URL=http://10.98.12.68:8085/v1
set VITA_LLM_KEY=2000^|sk-QnU3ZCYDtrLmxiPdaODCzchISrwnaQUL
set VITA_LLM_MODEL=GLM-4.7

REM 备用LLM（GLM-4.7 旧地址）
set VITA_LLM_FALLBACK_URL=http://10.98.12.75:38444/apiaccess/1770976378_glm47-20260213/v1
set VITA_LLM_FALLBACK_KEY=2000^|sk-QnU3ZCYDtrLmxiPdaODCzchISrwnaQUL
set VITA_LLM_FALLBACK_MODEL=GLM-4.7

echo.
echo ========================================
echo   VITA v15.1 - Service Startup
echo ========================================
echo.
echo Location: E:\vita
echo Python: D:\miniconda3\python.exe
echo URL: http://10.97.10.60:3000
echo.
echo Database: %VITA_DB_USER%@%VITA_DB_DSN%
echo.
echo Press Ctrl+C to stop the service
echo.

D:\miniconda3\python.exe -m streamlit run vita.py --server.port 3000 --server.address 0.0.0.0

echo.
echo Service stopped
pause
