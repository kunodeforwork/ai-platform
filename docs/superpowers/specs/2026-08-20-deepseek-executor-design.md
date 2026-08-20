# DeepSeek V4 Flash 执行器接入设计

## 目标

将现有 Agent 运行链路的默认回显执行器替换为 DeepSeek 官方 OpenAI 兼容 API，使 `POST /api/v1/agent-runs` 能返回 `deepseek-v4-flash` 的真实单轮回答，同时保持应用服务和 HTTP 契约稳定。

## 已确认决策

- 使用 `openai` Python SDK 调用 DeepSeek 的 OpenAI 兼容接口。
- 默认模型固定为 `deepseek-v4-flash`。
- 首版固定发送 `thinking: {"type": "disabled"}`，不开放请求级切换。
- API 密钥只从环境变量读取，不写入代码、文档示例值、日志或测试夹具。
- 本切片只实现同步、非流式、单轮文本对话。

## 配置

应用通过不可变配置对象读取以下环境变量：

| 环境变量 | 必填 | 默认值 | 用途 |
| --- | --- | --- | --- |
| `DEEPSEEK_API_KEY` | 是 | 无 | DeepSeek API 凭据 |
| `DEEPSEEK_BASE_URL` | 否 | `https://api.deepseek.com` | OpenAI 兼容基础地址 |
| `DEEPSEEK_MODEL` | 否 | `deepseek-v4-flash` | 模型标识 |

缺少密钥不会阻止 FastAPI 启动或 `/health` 响应。首次调用 Agent 运行接口时，执行器返回可识别的配置异常。

仓库新增 `.env.example`，只包含占位值；`.env` 必须被 Git 忽略。

## 架构与组件

### `DeepSeekSettings`

负责从环境变量构造并校验 DeepSeek 配置。它不持有客户端，不访问网络。

### `DeepSeekAgentExecutor`

实现现有 `AgentExecutor.execute(message: str) -> str` 协议。构造函数接收配置和可替换的 OpenAI 客户端，生产环境由默认依赖提供者装配，测试传入手写假客户端。

每次调用发送：

```python
client.chat.completions.create(
    model=settings.model,
    messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": message},
    ],
    stream=False,
    extra_body={"thinking": {"type": "disabled"}},
)
```

系统提示词保持最小化：说明助手服务于正泰企业场景，要求准确、简洁，信息不足时明确说明。首版不加入知识库、工具或动态 Agent 配置。

执行器只返回首个 choice 的文本内容。响应缺少 choice、message 或非空 content 时，视为无效上游响应。

### 依赖装配

`get_agent_run_service()` 继续作为 FastAPI 依赖覆盖点，但默认实现改为：

`DeepSeekSettings` → `OpenAI` 客户端 → `DeepSeekAgentExecutor` → `AgentRunService`

这样 API 和应用服务无需知道模型供应商，现有测试仍可通过依赖覆盖隔离外部调用。

## 错误契约

新增领域边界异常，并在 HTTP 层稳定映射：

| 场景 | HTTP 状态 | `error.code` |
| --- | ---: | --- |
| 未配置 `DEEPSEEK_API_KEY` | 503 | `deepseek_not_configured` |
| DeepSeek 请求超时 | 504 | `deepseek_timeout` |
| DeepSeek 限流 | 503 | `deepseek_rate_limited` |
| DeepSeek 拒绝 API 凭据 | 502 | `deepseek_authentication_failed` |
| 其他网络、服务端或无效响应 | 502 | `deepseek_upstream_error` |

错误响应统一为：

```json
{
  "error": {
    "code": "deepseek_timeout",
    "message": "DeepSeek request timed out"
  }
}
```

响应不得包含 API 密钥、SDK 原始异常正文、请求头或完整上游响应。现有输入校验 `422` 契约保持不变。

## 数据流

1. API 校验非空消息。
2. FastAPI 默认依赖惰性读取 DeepSeek 配置并创建服务。
3. `AgentRunService` 将消息交给 `DeepSeekAgentExecutor`。
4. 执行器调用同步 Chat Completions API，使用 `deepseek-v4-flash` 和禁用思考模式。
5. 正常文本映射为现有 `run_id/status/output` 响应。
6. 配置或上游错误转换为稳定的执行器异常，再由 HTTP 层转换为错误契约。

## 测试策略

- 配置单元测试：默认值、环境变量覆盖、缺少密钥。
- 执行器单元测试：精确请求参数、文本提取、空响应及各类 SDK 异常转换。
- API 测试：每个领域异常对应的状态码和安全错误体。
- 回归测试：健康检查、输入校验、应用服务委托和成功响应契约继续通过。
- 自动测试不访问 DeepSeek 网络，也不要求真实 API 密钥。
- README 提供显式的本地真实连通命令；不新增默认运行的在线集成测试。

## 非目标

- 多轮会话和上下文持久化
- 流式输出
- Thinking 模式切换
- 工具调用、知识库和 LangGraph
- 重试、熔断、指标及分布式追踪
- 数据库、鉴权和租户隔离

## 验收标准

- 配置 `DEEPSEEK_API_KEY` 后，现有 Agent 运行接口能返回 DeepSeek 文本回答。
- 发往 SDK 的模型、消息、`stream` 和 `thinking` 参数有自动测试保护。
- 未配置、超时、限流、认证和其他上游错误均返回规定的安全错误结构。
- `pytest` 与 `ruff check .` 全部通过。
- `.env` 和 API 密钥不会进入 Git 追踪文件。
