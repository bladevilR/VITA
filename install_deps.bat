@echo off
chcp 65001 >nul

echo.
echo ========================================
echo VITA - Install Dependencies
echo ========================================
echo.

cd /d E:\vita

echo Installing packages (this may take 5-10 minutes)...
echo.

echo [1/6] Upgrading pip...
.venv\Scripts\python.exe -m pip install --upgrade pip

echo.
echo [2/6] Installing streamlit...
.venv\Scripts\pip.exe install streamlit

echo.
echo [3/6] Installing pandas...
.venv\Scripts\pip.exe install pandas

echo.
echo [4/6] Installing faiss-cpu...
.venv\Scripts\pip.exe install faiss-cpu

echo.
echo [5/6] Installing oracledb...
.venv\Scripts\pip.exe install oracledb

echo.
echo [6/6] Installing requests and numpy...
.venv\Scripts\pip.exe install requests numpy

echo.
echo ========================================
echo Installation complete!
echo ========================================
echo.
echo Verifying installation...
echo.

.venv\Scripts\python.exe -c "import streamlit; print('✓ streamlit OK')"
.venv\Scripts\python.exe -c "import pandas; print('✓ pandas OK')"
.venv\Scripts\python.exe -c "import faiss; print('✓ faiss OK')"
.venv\Scripts\python.exe -c "import oracledb; print('✓ oracledb OK')"
.venv\Scripts\python.exe -c "import requests; print('✓ requests OK')"
.venv\Scripts\python.exe -c "import numpy; print('✓ numpy OK')"

echo.
echo All packages installed successfully!
echo You can now run: start_vita.bat
echo.
pause
