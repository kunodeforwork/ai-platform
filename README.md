# 正泰企业 AI Agent 平台

这是平台的最小可运行纵向切片：FastAPI 接收 Agent 运行请求，应用服务调用可替换的执行器，并返回标准化运行结果。默认执行器调用 DeepSeek V4 Flash。

## 本地运行

需要 Python 3.11 或更高版本。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
docker compose up -d postgres
$env:DATABASE_URL = "postgresql+psycopg://chint:chint-local-password@localhost:5432/chint_ai"
alembic upgrade head
pytest -v
$env:DEEPSEEK_API_KEY = "你的-DeepSeek-API-Key"
uvicorn chint_ai_platform.main:app --reload
```

也可以复制 [.env.example](.env.example) 查看支持的配置项。应用不会自动读取 `.env` 文件；请由 shell、容器或部署平台注入环境变量。应用也不会自动建表或迁移，部署时必须显式运行 `alembic upgrade head`。默认配置为：

- `DEEPSEEK_BASE_URL=https://api.deepseek.com`
- `DEEPSEEK_MODEL=deepseek-v4-flash`
- `thinking={"type":"disabled"}`（由服务固定发送）
- `DATABASE_URL=postgresql+psycopg://chint:chint-local-password@localhost:5432/chint_ai`（仅本地开发示例）

`DEEPSEEK_API_KEY` 是唯一必填项。缺少时健康检查仍可用，Agent 运行接口会返回 `503/deepseek_not_configured`。

服务启动后可访问：

- 健康检查：`GET http://127.0.0.1:8000/health`
- 创建 Agent：`POST http://127.0.0.1:8000/api/v1/agents`
- 查询 Agent：`GET http://127.0.0.1:8000/api/v1/agents/{agent_id}`
- 按 Agent 运行：`POST http://127.0.0.1:8000/api/v1/agents/{agent_id}/runs`
- Agent 运行：`POST http://127.0.0.1:8000/api/v1/agent-runs`
- 查询运行记录：`GET http://127.0.0.1:8000/api/v1/agent-runs/{run_id}`
- OpenAPI 文档：`http://127.0.0.1:8000/docs`

创建 Agent：

```powershell
$agent = Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/agents `
  -ContentType 'application/json' `
  -Body '{"name":"销售分析助手","description":"分析区域销售异常","system_prompt":"你是正泰销售分析助手，请给出简洁、可验证的分析。"}'
```

使用该 Agent 运行：

```powershell
Invoke-RestMethod -Method Post `
  -Uri "http://127.0.0.1:8000/api/v1/agents/$($agent.id)/runs" `
  -ContentType 'application/json' `
  -Body '{"message":"分析本月销售异常"}'
```

示例请求：

```powershell
Invoke-RestMethod -Method Post `
  -Uri http://127.0.0.1:8000/api/v1/agent-runs `
  -ContentType 'application/json' `
  -Body '{"message":"分析本月销售异常"}'
```

示例响应：

```json
{
  "run_id": "3b9d82b0-ae2f-4d92-9417-c9ea46dcfa1b",
  "status": "completed",
  "output": "分析本月销售异常"
}
```

每次通过上述两个运行接口发起的有效请求都会先持久化为 `running`，随后更新为
`completed` 或 `failed`。成功响应中的 `run_id` 可直接用于查询完整审计记录：

```powershell
Invoke-RestMethod -Method Get `
  -Uri "http://127.0.0.1:8000/api/v1/agent-runs/3b9d82b0-ae2f-4d92-9417-c9ea46dcfa1b"
```

DeepSeek 超时、限流、鉴权或上游错误的安全响应会在顶层返回同一个 `run_id`，
对应记录保存稳定的 `error_code`，不会保存原始异常、请求头、密钥或模型推理内容。
请求体校验失败（422）不会创建运行记录。

## 测试与当前边界

自动测试使用手写假客户端，不连接 DeepSeek，也不需要真实密钥。设置密钥并启动服务后，上面的示例请求就是显式的真实连通性检查。

Agent 配置与运行审计记录默认保存在 PostgreSQL 中，可供多个服务进程共享。日常自动测试使用临时 SQLite，不访问网络；设置独立的 `POSTGRES_TEST_DATABASE_URL` 后可运行显式 PostgreSQL 集成测试。

本切片不包含鉴权、租户隔离、任务队列、多轮会话、流式输出、工具调用或前端。`AgentExecutor` 协议仍是后续接入其他模型与编排框架的替换点。
