# 工作站包说明

本目录是工作站部署包，负责界面、钉钉、大模型、向量检索和最终答案生成。

## 工作站包负责什么

- 启动本地界面
- 接收钉钉消息
- 解析用户问题
- 生成向量并召回案例
- 调用重排与大模型
- 组合最终诊断结论

## 工作站包不负责什么

- 不直连 Oracle / Maximo
- 不执行 SQL
- 不保存数据库账号密码

## 直接怎么用

1. 把整个 `workstation_vita` 文件夹复制到工作站目录，例如 `E:\vita\workstation_vita`
2. 保持目录内 `.env`、`kb_zhipu.index`、`kb_zhipu_id_map.npy` 不变
3. 双击以下脚本之一

- `启动工作站界面.bat`：只启动界面
- `启动钉钉桥接.bat`：只启动钉钉桥接
- `启动工作站全套.bat`：界面和钉钉一起启动

## 默认端口

- 服务端接口端口：`3000`
- 工作站界面端口：`8501`

工作站界面端口只是本机界面端口，不影响服务端接口调用。

## 网络要求

- 需要通过内网访问服务端 `server_maximo`
- 需要访问本地或内网可达的大模型、向量、重排接口
- 如果要接钉钉，还需要工作站能连钉钉

工作站不需要固定 IP。

## 自测

命令行执行：

```powershell
runtime\python\python.exe self_test_diagnosis_workflow.py
runtime\python\python.exe generate_eval_report.py
```

也可以直接双击：

- `运行诊断自测.bat`

报告会输出到：

- `DIAGNOSIS_EVAL_REPORT.md`

## 附带资料

- `DIAGNOSIS_WORKFLOW_DESIGN.md`：诊断工作流设计文档
- `diagnosis_eval_cases.json`：验收样例集
- `DIAGNOSIS_EVAL_REPORT.md`：最近一次验收报告
