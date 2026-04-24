@echo off
setlocal

set ROOT=%~dp0
cd /d "%ROOT%"

start "VITA UI" cmd /k "%ROOT%start_workstation_ui.bat"
start "VITA DingTalk" cmd /k "%ROOT%start_dingtalk_bridge.bat"

endlocal
