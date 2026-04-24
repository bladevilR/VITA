# 分体部署总览

当前仓库已经拆成两套可独立部署的目录：

- `packages/server_maximo`
- `packages/workstation_vita`

## 服务端包

目录：`packages/server_maximo`

职责：

- 直连 Oracle / Maximo
- 执行全部 SQL
- 生成统计、责任归属、诊断支持数据
- 对外提供带令牌保护的 HTTP 接口

## 工作站包

目录：`packages/workstation_vita`

职责：

- 界面交互
- 钉钉桥接
- 查询解析
- 向量召回
- 重排
- 最终大模型生成答案

## 网络要求

- 工作站不需要固定 IP
- 只要工作站能通过内网访问服务端接口即可
- 访问控制通过 `X-Vita-Token` 完成，不依赖客户端 IP 白名单

## 需要保留的文件

只有工作站包需要向量文件：

- `kb_zhipu.index`
- `kb_zhipu_id_map.npy`

两套包都已经内置：

- 可直接使用的 `.env`
- `runtime\python`
- `vendor\` 依赖

正常情况下，整包复制到目标机器目录后即可启动。
