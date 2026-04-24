$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$releaseRoot = Join-Path $root "release"
$targetRoot = Join-Path $releaseRoot $timestamp

New-Item -ItemType Directory -Force -Path $targetRoot | Out-Null

function Copy-Package {
    param(
        [string]$SourceName
    )

    $source = Join-Path $root $SourceName
    $target = Join-Path $targetRoot $SourceName
    New-Item -ItemType Directory -Force -Path $target | Out-Null

    $null = robocopy $source $target /E /R:1 /W:1 /XD __pycache__ .pytest_cache /XF _tmp_ui_out.log _tmp_ui_err.log
    if ($LASTEXITCODE -ge 8) {
        throw "复制 $SourceName 失败，robocopy 退出码：$LASTEXITCODE"
    }
}

Copy-Package -SourceName "server_maximo"
Copy-Package -SourceName "workstation_vita"

$guide = @"
VITA split deployment package

generated_at=$timestamp

server_folder=server_maximo
server_example_path=E:\server_maximo
server_start=start_server.bat

workstation_folder=workstation_vita
workstation_example_path=E:\vita\workstation_vita
workstation_ui_start=start_workstation_ui.bat
workstation_dingtalk_start=start_dingtalk_bridge.bat
workstation_all_start=start_workstation_all.bat

server_port=3000
ui_port=8501
"@

Set-Content -Path (Join-Path $targetRoot "DEPLOY_INFO.txt") -Value $guide -Encoding UTF8
Write-Output "RELEASE_PATH=$targetRoot"
