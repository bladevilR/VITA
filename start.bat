@echo off

cd /d E:\vita

echo.
echo ========================================
echo   VITA v15.1 - Starting Service
echo ========================================
echo.
echo Service: http://localhost:3003
echo.
echo Press Ctrl+C to stop
echo.

E:\vita\.venv\Scripts\python.exe -m streamlit run vita.py --server.port 3003 --server.address 0.0.0.0

pause
