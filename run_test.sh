#!/bin/bash
# VITA 性能测试脚本 - 启动应用并监控日志

echo "========================================"
echo "VITA 性能测试 - 本地版"
echo "========================================"
echo ""

# 检查 streamlit 是否安装
if ! command -v streamlit &> /dev/null; then
    echo "错误: streamlit 未安装"
    echo "请运行: pip install streamlit"
    exit 1
fi

echo "启动 Streamlit 应用..."
echo "日志将显示各阶段性能数据"
echo ""
echo "请在浏览器中打开应用并测试以下查询："
echo "  1. 3号线横山站ISCS工作站黑屏怎么办"
echo "  2. AFC闸机不能刷卡"
echo "  3. FAS报警主机故障"
echo ""
echo "按 Ctrl+C 停止应用"
echo "========================================"
echo ""

# 启动应用，日志输出到终端和文件
streamlit run vita.py --server.port 8501 --server.headless true 2>&1 | tee performance_test.log
