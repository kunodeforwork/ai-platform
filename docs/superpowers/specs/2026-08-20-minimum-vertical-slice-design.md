# 正泰企业 AI Agent 平台：最小可运行纵向切片设计

## 目标

建立一个可本地启动、可自动测试的 FastAPI 基础工程，并让一条 Agent 运行请求完整穿过 HTTP、应用服务和执行器边界。

## 范围

- `GET /health` 返回服务健康状态。
- `POST /api/v1/agent-runs` 接收非空 `message`，返回 `run_id`、`status` 和 `output`。
- 首个执行器为确定性回显实现，便于离线运行与测试；真实 LLM 后续通过同一协议替换。
- FastAPI 依赖注入负责装配应用服务，测试可覆盖依赖。
- 统一使用 Pydantic 校验输入，非法请求沿用 FastAPI 的 `422` 契约。

## 非目标

本切片不包含数据库、鉴权、租户隔离、异步任务队列、真实模型调用、流式输出、Docker 或前端。

## 结构与数据流

`POST /api/v1/agent-runs` → 路由校验请求 → `AgentRunService.run(message)` → `AgentExecutor.execute(message)` → 映射为 HTTP 响应。

执行器协议与 HTTP 层隔离，使模型供应商、编排框架和持久化可以独立演进。运行标识由应用服务生成，状态在本切片中固定为 `completed`。

## 错误处理

空字符串或纯空白消息在请求模型处拒绝并返回 `422`。执行器异常暂不转换为业务错误，由 FastAPI 返回服务器错误；后续接入真实外部服务时再增加稳定错误码和可重试分类。

## 测试策略

- API 测试覆盖健康检查、成功运行和输入校验。
- 应用服务单元测试覆盖消息转交、输出映射及运行标识格式。
- 测试使用真实回显执行器或轻量手写桩，不连接外部服务。

## 验收标准

- `pytest` 全部通过。
- `uvicorn chint_ai_platform.main:app --reload` 可启动服务。
- OpenAPI 自动暴露两个端点，成功请求返回稳定 JSON 结构。
