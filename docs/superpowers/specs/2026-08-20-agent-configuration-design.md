# Agent 配置管理与按 ID 运行设计

## 目标

在现有 DeepSeek 单 Agent 调用链路之上增加最小 Agent 配置能力：调用方可以创建一个包含系统提示词的 Agent、按 ID 查询它，并通过该 Agent 的 ID 发起运行。首版使用进程内仓储，为下一切片替换 PostgreSQL 留出稳定接口。

## 已确认决策

- 新增 `POST /api/v1/agents/{agent_id}/runs` 作为显式 Agent 运行入口。
- 保留现有 `POST /api/v1/agent-runs`，继续使用平台默认系统提示词，避免破坏现有调用方。
- 使用仓储协议隔离存储实现，首版提供线程安全的内存仓储。
- 本切片不实现列表、更新、删除、版本、权限或持久化。

## 领域模型

`Agent` 是不可变领域对象：

| 字段 | 类型 | 规则 |
| --- | --- | --- |
| `id` | UUID 字符串 | 服务端生成 UUID4 |
| `name` | 字符串 | 去除首尾空白后长度 1–100 |
| `description` | 字符串 | 去除首尾空白后长度 0–500，默认空字符串 |
| `system_prompt` | 字符串 | 去除首尾空白后长度 1–4000 |
| `created_at` | UTC 时间 | 服务端生成，API 使用 ISO 8601 格式 |

本切片中 Agent 创建后不可修改。

## 组件边界

### `AgentRepository`

仓储协议只声明：

```python
class AgentRepository(Protocol):
    def add(self, agent: Agent) -> None: ...
    def get(self, agent_id: str) -> Agent | None: ...
```

调用方不依赖字典、锁或未来数据库细节。

### `InMemoryAgentRepository`

使用进程内字典保存 Agent，并用互斥锁保护读取和写入。实例由缓存的 FastAPI 依赖提供者持有，因此同一进程内的创建和查询可见。进程重启或多进程部署不会共享数据，这是本切片的明确限制。

### `AgentService`

负责生成 ID 和 UTC 创建时间、创建 Agent、查询 Agent。查询缺失时抛出 `AgentNotFoundError`；HTTP 层将其映射为稳定的 `404` 错误响应。

### `AgentRunService`

运行服务调整为接受系统提示词和用户消息：

```python
run(system_prompt: str, message: str) -> AgentRun
```

它仍负责运行 ID 和完成状态。显式 Agent 运行由一个应用服务先查询 Agent，再将 `agent.system_prompt` 和用户消息交给运行服务。

### `AgentExecutor`

执行器协议调整为：

```python
execute(system_prompt: str, message: str) -> str
```

`DeepSeekAgentExecutor` 不再持有固定系统提示词；它精确发送调用方提供的系统提示词。兼容入口由平台常量提供原有默认提示词。

## HTTP API

### 创建 Agent

`POST /api/v1/agents`

请求：

```json
{
  "name": "销售分析助手",
  "description": "分析区域销售异常",
  "system_prompt": "你是正泰销售分析助手，请基于输入给出简洁、可验证的分析。"
}
```

成功返回 `201`：

```json
{
  "id": "5b1c53ef-6cd7-4537-81b6-d37ef87c5f69",
  "name": "销售分析助手",
  "description": "分析区域销售异常",
  "system_prompt": "你是正泰销售分析助手，请基于输入给出简洁、可验证的分析。",
  "created_at": "2026-08-20T09:30:00Z"
}
```

名称、描述和系统提示词由 Pydantic 在 HTTP 边界完成去空白与长度校验，失败沿用 FastAPI `422` 契约。

### 查询 Agent

`GET /api/v1/agents/{agent_id}`

- 存在时返回 `200` 和与创建响应相同的数据结构。
- 不存在时返回 `404`：

```json
{
  "error": {
    "code": "agent_not_found",
    "message": "Agent not found"
  }
}
```

路径参数先校验为 UUID；格式非法时返回 `422`，格式合法但不存在时返回 `404`。

### 按 Agent ID 运行

`POST /api/v1/agents/{agent_id}/runs`

请求继续使用：

```json
{"message": "分析本月销售异常"}
```

成功响应保持现有 `201` 契约：

```json
{
  "run_id": "d6109938-c9ba-4bc0-a20a-27e1b1fceb67",
  "status": "completed",
  "output": "发现华东区域销售异常"
}
```

Agent 不存在时返回同一 `404/agent_not_found` 错误。输入空白仍返回 `422`，且不会调用仓储或 DeepSeek。

### 兼容运行入口

`POST /api/v1/agent-runs` 保持路径、请求和响应不变。内部使用原有平台默认系统提示词，不查询 Agent 仓储。本切片不在 OpenAPI 中标记弃用。

## 数据流

创建：HTTP 校验 → `AgentService.create` → 生成 ID/时间 → `AgentRepository.add` → 映射响应。

查询：HTTP 校验 UUID → `AgentService.get` → `AgentRepository.get` → 返回 Agent 或抛出 `AgentNotFoundError`。

按 ID 运行：HTTP 校验 → 查询 Agent → `AgentRunService.run(agent.system_prompt, message)` → `DeepSeekAgentExecutor.execute(system_prompt, message)` → 返回运行结果。

兼容运行：HTTP 校验 → `AgentRunService.run(DEFAULT_SYSTEM_PROMPT, message)` → DeepSeek → 返回运行结果。

## 错误处理

- Agent 缺失统一映射为 `404/agent_not_found`，不包含仓储内部信息。
- DeepSeek 配置和上游错误保持现有安全错误契约。
- HTTP 输入错误保持 `422`。
- 内存仓储不产生面向 HTTP 的其他错误类型。

## 测试策略

- 领域与仓储测试：创建字段、UUID、UTC 时间、add/get 和未知 ID。
- 并发仓储测试：并行写入后所有 Agent 均可读取，保护锁语义。
- 应用服务测试：显式 Agent 运行准确传递该 Agent 的系统提示词和用户消息。
- DeepSeek 执行器测试：请求中的 system 消息来自调用参数，且仍固定 `deepseek-v4-flash`、`stream=False`、`thinking: disabled`。
- API 测试：创建、查询、字段校验、未知 Agent、按 ID 成功运行及兼容入口。
- 自动测试继续使用手写假对象，不访问真实 DeepSeek API。

## 非目标

- Agent 列表、更新、删除和版本管理
- PostgreSQL、迁移或 ORM
- 多进程数据共享和服务重启恢复
- 用户、角色、租户与权限
- 多轮对话、流式输出、工具调用和知识库
- Agent 名称唯一性

## 验收标准

- 可以通过 HTTP 创建 Agent 并按 ID 查询完全相同的配置。
- 可以通过 Agent ID 运行，并有测试证明该 Agent 的系统提示词被发送给 DeepSeek。
- 原有 `/api/v1/agent-runs` 成功、校验及 DeepSeek 错误契约保持兼容。
- 未知 Agent 返回稳定、安全的 `404` 错误结构。
- 内存仓储在并发测试中不丢失已完成写入。
- `pytest`、`ruff check .` 和 OpenAPI 冒烟检查全部通过。
