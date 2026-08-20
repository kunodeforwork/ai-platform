# 正泰企业 AI Agent 平台

这是平台的最小可运行纵向切片：FastAPI 接收 Agent 运行请求，应用服务调用可替换的执行器，并返回标准化运行结果。当前执行器为确定性回显实现，不访问外部模型。

## 本地运行

需要 Python 3.11 或更高版本。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
pytest -v
uvicorn chint_ai_platform.main:app --reload
```

服务启动后可访问：

- 健康检查：`GET http://127.0.0.1:8000/health`
- Agent 运行：`POST http://127.0.0.1:8000/api/v1/agent-runs`
- OpenAPI 文档：`http://127.0.0.1:8000/docs`

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

## 当前边界

本切片不包含数据库、鉴权、租户隔离、任务队列、真实 LLM、流式输出、Docker 或前端。`AgentExecutor` 协议是后续接入真实模型与编排框架的替换点。
