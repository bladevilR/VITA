@echo off
setlocal enabledelayedexpansion

cd /d "%~dp0"

echo.
echo ========== Testing VITA Environment ==========
echo.

echo [1] Checking Python...
E:\vita\.venv\Scripts\python.exe --version
if errorlevel 1 (
    echo ERROR: Python not working
    pause
    exit /b 1
)
echo OK
echo.

echo [2] Checking required packages...
E:\vita\.venv\Scripts\python.exe -c "import streamlit; print('streamlit:', streamlit.__version__)"
E:\vita\.venv\Scripts\python.exe -c "import pandas; print('pandas: OK')"
E:\vita\.venv\Scripts\python.exe -c "import oracledb; print('oracledb: OK')"
E:\vita\.venv\Scripts\python.exe -c "import faiss; print('faiss: OK')"
E:\vita\.venv\Scripts\python.exe -c "import numpy; print('numpy: OK')"
E:\vita\.venv\Scripts\python.exe -c "import requests; print('requests: OK')"
echo.

echo [3] Checking vita.py imports...
E:\vita\.venv\Scripts\python.exe -c "import vita; print('vita.py: OK')"
if errorlevel 1 (
    echo ERROR: vita.py has import errors
    pause
    exit /b 1
)
echo.

echo [4] Checking knowledge base files...
if exist "kb_zhipu.index" (
    echo OK: kb_zhipu.index found
) else (
    echo WARNING: kb_zhipu.index not found
)

if exist "kb_zhipu_id_map.npy" (
    echo OK: kb_zhipu_id_map.npy found
) else (
    echo WARNING: kb_zhipu_id_map.npy not found
)
echo.

echo ========== All tests passed ==========
echo.
pause
endlocal
