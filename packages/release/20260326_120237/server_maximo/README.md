# 服务端包说明

本目录是服务端部署包，负责连接 Maximo / Oracle，并对外提供固定接口。

## 服务端包负责什么

- 连接 Oracle / Maximo
- 执行 SQL
- 返回统计结果
- 返回责任归属结果
- 返回诊断支持案例与聚合数据

## 服务端包不负责什么

- 不跑界面
- 不跑钉钉
- 不跑大模型
- 不做 embedding、重排、FAISS

## 直接怎么用

1. 把整个 `server_maximo` 文件夹复制到服务器目录，例如 `E:\server_maximo`
2. 保持目录内 `.env` 不变
3. 双击：

- `启动服务端接口.bat`

或者：

- `start_server.bat`

## 默认端口

- 服务端接口端口：`3000`

## 认证方式

如果 `.env` 中配置了 `VITA_SERVER_API_TOKEN`，调用方必须带：

```text
X-Vita-Token: <你的令牌>
```

这意味着工作站可以在任意内网可达位置调试，不依赖固定 IP。

## 当前接口

- `GET /healthz`
- `POST /statistics/run`
- `POST /responsibility/run`
- `POST /diagnosis/support`
- `POST /diagnosis/support-batch`

## 说明

服务端包已经内置：

- `runtime\python`
- `vendor\` 依赖

正常情况下，整包复制到目标服务器后即可启动。
