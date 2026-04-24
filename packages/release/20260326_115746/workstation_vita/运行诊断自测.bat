@echo off
setlocal

set ROOT=%~dp0
cd /d "%ROOT%"
set PYTHON_EXE=%ROOT%runtime\python\python.exe

if not exist "%PYTHON_EXE%" set PYTHON_EXE=python

echo [1/2] 运行诊断工作流自测...
"%PYTHON_EXE%" -X utf8 "%ROOT%self_test_diagnosis_workflow.py"
if errorlevel 1 (
    echo.
    echo [错误] 自测未通过。
    pause
    exit /b 1
)

echo.
echo [2/2] 生成验收报告...
"%PYTHON_EXE%" -X utf8 "%ROOT%generate_eval_report.py"
if errorlevel 1 (
    echo.
    echo [错误] 报告生成过程中存在失败用例，请查看 DIAGNOSIS_EVAL_REPORT.md
    pause
    exit /b 1
)

echo.
echo [完成] 自测通过，报告已生成。
pause

endlocal
