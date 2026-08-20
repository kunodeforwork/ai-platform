# 正泰企业 AI Agent 平台

这是平台的最小可运行纵向切片：FastAPI 接收 Agent 运行请求，应用服务调用可替换的执行器，并返回标准化运行结果。默认执行器调用 DeepSeek V4 Flash。

## 本地运行

需要 Python 3.11 或更高版本。

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
pytest -v
$env:DEEPSEEK_API_KEY = "你的-DeepSeek-API-Key"
uvicorn chint_ai_platform.main:app --reload
```

也可以复制 [.env.example](.env.example) 查看支持的配置项。应用不会自动读取 `.env` 文件；请由 shell、容器或部署平台注入环境变量。默认配置为：

- `DEEPSEEK_BASE_URL=https://api.deepseek.com`
- `DEEPSEEK_MODEL=deepseek-v4-flash`
- `thinking={"type":"disabled"}`（由服务固定发送）

`DEEPSEEK_API_KEY` 是唯一必填项。缺少时健康检查仍可用，Agent 运行接口会返回 `503/deepseek_not_configured`。

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

## 测试与当前边界

自动测试使用手写假客户端，不连接 DeepSeek，也不需要真实密钥。设置密钥并启动服务后，上面的示例请求就是显式的真实连通性检查。

本切片不包含数据库、鉴权、租户隔离、任务队列、多轮会话、流式输出、工具调用、Docker 或前端。`AgentExecutor` 协议仍是后续接入其他模型与编排框架的替换点。
