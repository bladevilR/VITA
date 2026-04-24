@echo off
REM VITA 本地测试启动脚本

echo ========================================
echo VITA 性能测试 - 本地版
echo ========================================
echo.

REM 设置本地测试环境变量（如果需要）
REM set VITA_LLM_URL=http://localhost:8085/v1
REM set VITA_DB_HOST=localhost

echo 启动 Streamlit 应用...
echo 日志将显示各阶段性能数据
echo.
echo 请在浏览器中打开应用并测试以下查询：
echo   1. 3号线横山站ISCS工作站黑屏怎么办
echo   2. AFC闸机不能刷卡
echo   3. FAS报警主机故障
echo.
echo 按 Ctrl+C 停止应用
echo ========================================
echo.

streamlit run vita.py --server.port 8501 --server.headless true

pause
