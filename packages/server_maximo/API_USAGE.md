# 服务端接口使用说明

## 范围

本服务不是通用数据库网关，不开放任意 SQL。

当前代码只基于以下业务表：

- `MAXIMO.SR`

对外提供固定 HTTP 接口：

- `GET /healthz`
- `POST /statistics/run`
- `POST /responsibility/run`
- `POST /diagnosis/support`
- `POST /diagnosis/support-batch`

## 基础地址

默认端口是 `3000`，基础地址示例：

```text
http://<服务器IP>:3000
```

如果 `.env` 中修改了：

```text
VITA_SERVER_PORT=3003
```

那么基础地址就是：

```text
http://<服务器IP>:3003
```

## 认证

如果配置了 `VITA_SERVER_API_TOKEN`，每次请求都必须带：

```text
X-Vita-Token: <你的令牌>
```

## 1. 健康检查

请求：

```bash
curl -X GET "http://<服务器IP>:3000/healthz" ^
  -H "X-Vita-Token: <你的令牌>"
```

返回示例：

```json
{
  "status": "ok",
  "db_available": true,
  "db_message": "正常",
  "dsn": "10.97.4.7:1521/eamprod"
}
```

## 2. 故障统计

地址：

```text
POST /statistics/run
```

请求体示例：

```json
{
  "entities": {
    "line_num": "3",
    "station_name": "xxx",
    "specialty": "信号",
    "device": "道岔",
    "fault_phenomenon": "无表示",
    "time_range": {
      "start_date": "2026-03-01",
      "end_date": "2026-03-25"
    },
    "compare_dimension": "line"
  },
  "query_type": "count"
}
```

`query_type` 可选：

- `count`：明细统计
- `ranking`：高频故障排名
- `comparison`：按线路 / 车站 / 专业比较

## 3. 责任归属

地址：

```text
POST /responsibility/run
```

请求体示例：

```json
{
  "entities": {
    "line_num": "3",
    "specialty": "信号",
    "device": "道岔"
  }
}
```

## 4. 单层诊断支持

地址：

```text
POST /diagnosis/support
```

请求体示例：

```json
{
  "user_query": "3号线某站道岔无表示，想看类似案例",
  "entities": {
    "line_num": "3",
    "station_name": "xxx",
    "specialty": "信号",
    "device": "道岔",
    "fault_phenomenon": "无表示"
  },
  "vector_candidate_ids": ["10001", "10002", "10003"],
  "limit": 20
}
```

## 5. 批量诊断支持

地址：

```text
POST /diagnosis/support-batch
```

这个接口用于工作站一次性提交多层检索计划，减少往返调用次数。

请求体示例：

```json
{
  "user_query": "陆慕站综合监控工作站黑屏了怎么办",
  "layers": [
    {
      "layer_id": "direct_exact",
      "label": "直接匹配",
      "bucket": "direct",
      "evidence_level": "direct",
      "priority": 1,
      "entities": {
        "station_name": "陆慕站",
        "specialty": "ISCS",
        "device": "综合监控工作站",
        "fault_phenomenon": "黑屏"
      },
      "vector_candidate_ids": ["10001", "10002"],
      "limit": 20
    },
    {
      "layer_id": "station_same_device",
      "label": "本站同设备历史",
      "bucket": "station",
      "evidence_level": "history",
      "priority": 2,
      "entities": {
        "station_name": "陆慕站",
        "specialty": "ISCS",
        "device": "综合监控工作站",
        "fault_phenomenon": null
      },
      "vector_candidate_ids": [],
      "limit": 20
    }
  ]
}
```

## Python 调用示例

```python
import requests

base_url = "http://<服务器IP>:3000"
token = "<你的令牌>"

headers = {
    "Content-Type": "application/json",
    "X-Vita-Token": token,
}

payload = {
    "entities": {
        "line_num": "3",
        "specialty": "信号",
        "device": "道岔",
    }
}

resp = requests.post(
    f"{base_url}/responsibility/run",
    headers=headers,
    json=payload,
    timeout=30,
)

print(resp.status_code)
print(resp.json())
```

## 对外提供时要给什么

只需要给调用方四项：

- 服务端 IP 或域名
- 端口，例如 `3000`
- API 令牌
- 请求示例

示例：

```text
基础地址：http://10.10.10.20:3000
令牌：<你的令牌>
```

## 部署检查

要让别人调用成功，至少确认：

- 服务进程已经启动
- 服务器防火墙已放行接口端口
- 调用方能访问服务器网络地址
- Oracle 数据库可从服务器访问

## 重要限制

本包不是通用数据库查询代理。

如果后续要查别的表，必须在后端新增明确接口并写对应 SQL，不能直接放开任意查库。
