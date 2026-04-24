# DingTalk 本机实际配置说明

注意：

- 本文档包含真实密钥、真实 webhook、真实本地网关令牌。
- 仅用于在另一台电脑迁移或配置另一个内部工具。
- 不要提交到公开仓库，不要发到公开群。
- 如果密钥已经在聊天工具里暴露过，建议后续旋转。

---

## 1. 这套钉钉能力的真实接法

当前这台机器上的钉钉机器人不是靠固定 webhook 收消息。

实际是三段：

1. 钉钉企业应用通过 `clientId + clientSecret` 建立 Stream 长连接收消息
2. 私聊和群里 `@` 的即时回复通过回调里的 `sessionWebhook` 返回
3. 主动推送通过 `robotCode + 钉钉 OpenAPI` 调用

所以：

- 如果另一个工具要“接收私聊 / 接收群里 @”：
  - 需要用企业应用凭据接 Stream，不是只拿 webhook
- 如果另一个工具只要“主动往群里或用户发消息”：
  - 可以走 `robotCode + OpenAPI`
- 如果另一个工具只要“向某个现成群机器人 webhook 发消息”：
  - 可以直接用固定 webhook
  - 但这不是当前 OpenClaw 主聊天通道

---

## 2. 钉钉企业应用真实凭据

来源文件：

- `E:\workstation_143\clawbot\configs\dingtalk\env.local.ps1`

当前真实值：

```powershell
$env:DINGTALK_CLIENT_ID = "ding4dekfrn8mm9etpby"
$env:DINGTALK_CLIENT_SECRET = "zbcfXugTMQmGd_-NEjM3Rs1JffwhIUmZf_Ozh12BuBE25nvq6SMQoSTUC4zyPDiv"
$env:DINGTALK_ROBOT_CODE = "ding4dekfrn8mm9etpby"
```

说明：

- `DINGTALK_CLIENT_ID`
  - 企业应用 AppKey / Client ID
- `DINGTALK_CLIENT_SECRET`
  - 企业应用 AppSecret / Client Secret
- `DINGTALK_ROBOT_CODE`
  - 机器人编码
  - 当前和 `clientId` 一样

---

## 3. 固定 webhook

这个地址是现成可用的固定 webhook。

```text
https://oapi.dingtalk.com/robot/send?access_token=e8de26946d0880a1182926a46287560909cade404f93d71068f5a7bcd62f0002
```

用途说明：

- 可以给“另一个工具”直接发消息到对应机器人/群
- 适合简单主动推送
- 不适合接收私聊或群里 `@`
- 不是当前 OpenClaw 主聊天链路的入站方式

---

## 4. OpenClaw 当前钉钉配置

来源文件：

- `E:\workstation_143\clawbot\configs\dingtalk\openclaw.json`

当前有效配置：

```json
{
  "channels": {
    "dingtalk": {
      "enabled": true,
      "clientId": "${DINGTALK_CLIENT_ID}",
      "clientSecret": "${DINGTALK_CLIENT_SECRET}",
      "robotCode": "${DINGTALK_ROBOT_CODE}",
      "useConnectionManager": false,
      "dmPolicy": "open",
      "groupPolicy": "open",
      "allowFrom": ["*"],
      "messageType": "markdown",
      "debug": false
    }
  },
  "gateway": {
    "mode": "local",
    "auth": {
      "mode": "token",
      "token": "77fea669008dd652a542ba443ca1932999ad861823734f87"
    }
  },
  "plugins": {
    "enabled": true,
    "allow": ["dingtalk"],
    "entries": {
      "dingtalk": {
        "enabled": true
      }
    }
  }
}
```

关键信息：

- 私聊策略：`open`
- 群聊策略：`open`
- 回复格式：`markdown`
- 插件：`dingtalk`
- 本地网关认证 token：
  - `77fea669008dd652a542ba443ca1932999ad861823734f87`

这个 token 只有在“另一个工具要直接连接本地 OpenClaw 网关”时才需要。

---

## 5. 当前运行时信息

来源：

- `C:\Users\user\AppData\Local\Temp\openclaw\openclaw-2026-03-25.log`

当前这台机器上 DingTalk 网关的运行信息：

- 机器名：`1603LS-1`
- 模型：`gz-aigw/DeepSeek-V3.1`
- DingTalk 网关 WebSocket：
  - `ws://127.0.0.1:18789`
  - `ws://[::1]:18789`
- Browser control：
  - `http://127.0.0.1:18791/`
- 日志文件：
  - `C:\Users\user\AppData\Local\Temp\openclaw\openclaw-2026-03-25.log`

注意：

- `18789` 是 DingTalk 这套本地网关
- `18793` 是 WeChat 那套本地网关，不是 DingTalk

---

## 6. 启动方式

### 6.1 单独启动 DingTalk

入口：

- `E:\workstation_143\start_dingtalk_gateway.bat`

它实际调用：

- `E:\workstation_143\clawbot\start_dingtalk_gateway.ps1`

启动脚本做的事情：

1. 读取 `E:\workstation_143\clawbot\configs\dingtalk\env.local.ps1`
2. 设置 `OPENCLAW_CONFIG_PATH=E:\workstation_143\clawbot\configs\dingtalk\openclaw.json`
3. 设置 `OPENCLAW_STATE_DIR=E:\workstation_143\clawbot\configs\dingtalk\state`
4. 启动 `E:\workstation_143\clawbot\openclaw.mjs gateway`

### 6.2 通过 all 启动

入口：

- `E:\workstation_143\start_all_143.bat`

说明：

- `all` 会同时启动 DingTalk Gateway 和 WeChat Capture
- 这是两套 OpenClaw
- 钉钉是其中一套，不是重复启动两个钉钉网关

---

## 7. 当前插件和代码位置

钉钉插件实际加载位置：

- `E:\workstation_143\clawbot\configs\dingtalk\state\extensions\dingtalk`

关键文件：

- 收消息入口：
  - `E:\workstation_143\clawbot\configs\dingtalk\state\extensions\dingtalk\src\channel.ts`
- 消息处理：
  - `E:\workstation_143\clawbot\configs\dingtalk\state\extensions\dingtalk\src\inbound-handler.ts`
- 发送消息：
  - `E:\workstation_143\clawbot\configs\dingtalk\state\extensions\dingtalk\src\send-service.ts`
- 配置约束：
  - `E:\workstation_143\clawbot\configs\dingtalk\state\extensions\dingtalk\src\config-schema.ts`

当前已经加过一条入站诊断日志：

- `DingTalk callback received: ...`

它用于判断群里 `@` 的消息有没有真正到本地。

---

## 8. 主动发送接口的真实用法

### 8.1 通过企业应用主动发用户

接口：

```text
POST https://api.dingtalk.com/v1.0/robot/oToMessages/batchSend
```

头：

```text
x-acs-dingtalk-access-token: <access_token>
Content-Type: application/json
```

请求体示例：

```json
{
  "robotCode": "ding4dekfrn8mm9etpby",
  "msgKey": "sampleText",
  "msgParam": "{\"content\":\"你好\"}",
  "userIds": ["用户ID"]
}
```

### 8.2 通过企业应用主动发群

接口：

```text
POST https://api.dingtalk.com/v1.0/robot/groupMessages/send
```

头：

```text
x-acs-dingtalk-access-token: <access_token>
Content-Type: application/json
```

请求体示例：

```json
{
  "robotCode": "ding4dekfrn8mm9etpby",
  "msgKey": "sampleMarkdown",
  "msgParam": "{\"title\":\"通知\",\"text\":\"## 通知\\n\\n正文\"}",
  "openConversationId": "群会话ID"
}
```

说明：

- 这条才是当前 OpenClaw 用于主动发消息的真实接口
- 不是固定 webhook

---

## 9. 会话内回复的真实用法

当前 OpenClaw 对私聊和群里 `@` 的即时回复，走的是 DingTalk 回调里带回来的 `sessionWebhook`。

这类地址特点：

- 动态产生
- 每条会话上下文里都有
- 适合“收到消息之后立刻回复”
- 不适合提前写死在另一个工具里长期保存

如果另一个工具只是要实现“收到 DingTalk 消息后立即回复当前会话”，就应该：

1. 用 `clientId + clientSecret` 接 Stream
2. 从回调里拿到 `sessionWebhook`
3. 对 `sessionWebhook` 发消息

文本示例：

```json
{
  "msgtype": "text",
  "text": {
    "content": "这是会话内回复"
  }
}
```

Markdown 示例：

```json
{
  "msgtype": "markdown",
  "markdown": {
    "title": "处理结果",
    "text": "## 处理结果\n\n正文"
  }
}
```

---

## 10. 当前定时报表推送配置

来源文件：

- `E:\workstation_143\tools\dingtalk_push\push_config.json`

当前配置：

```json
{
  "channel": "dingtalk",
  "target": "user:011122012237767669",
  "openclawScript": "clawbot/openclaw.mjs",
  "configPath": "clawbot/configs/dingtalk/openclaw.json",
  "stateDir": "clawbot/configs/dingtalk/state",
  "envScript": "clawbot/configs/dingtalk/env.local.ps1"
}
```

说明：

- 当前定时推送默认目标是：
  - `user:011122012237767669`
- 这是“主动发用户”的现成目标
- 如果迁移到另一台电脑继续跑报表，这段配置也要一起带上

---

## 11. 另一台电脑如何迁移

### 11.1 如果另一个工具只要发消息

最简单方式有两种：

#### 方式 A：直接用固定 webhook

适合：

- 简单群通知
- 不需要收消息
- 不需要私聊
- 不需要群里 `@` 触发

要带走的内容：

- 固定 webhook 地址

#### 方式 B：用企业应用主动发送接口

适合：

- 发用户
- 发群
- 后续扩展空间更大

要带走的内容：

- `clientId`
- `clientSecret`
- `robotCode`

### 11.2 如果另一个工具也要收消息

必须带走：

- `clientId`
- `clientSecret`

然后在另一台电脑上：

1. 建 DingTalk Stream 连接
2. 接收机器人回调
3. 使用回调里的 `sessionWebhook` 回复

固定 webhook 无法替代这条链路。

### 11.3 如果另一台电脑要完整复制当前 OpenClaw 钉钉网关

至少复制下面这些文件和配置：

- `E:\workstation_143\clawbot\configs\dingtalk\env.local.ps1`
- `E:\workstation_143\clawbot\configs\dingtalk\openclaw.json`
- `E:\workstation_143\start_dingtalk_gateway.bat`
- `E:\workstation_143\clawbot\start_dingtalk_gateway.ps1`
- `E:\workstation_143\clawbot\configs\dingtalk\state\extensions\dingtalk`

如果还要带定时报表：

- `E:\workstation_143\tools\dingtalk_push\push_config.json`

---

## 12. 一页纸结论

如果另一个工具只想知道“到底用哪个接口”：

### 接收私聊 / 接收群里 `@`

用：

- `clientId + clientSecret + DingTalk Stream`

### 回复当前这次会话

用：

- 回调里的 `sessionWebhook`

### 主动发消息

用：

- `robotCode + access_token + DingTalk OpenAPI`

### 简单群通知

也可以直接用：

- 固定 webhook

但这条不是当前 OpenClaw 主聊天链路。
