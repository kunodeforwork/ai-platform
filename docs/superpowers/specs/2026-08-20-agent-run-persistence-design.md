# Agent 运行记录持久化设计

## 目标

持久化每次 Agent 运行的输入、最终输出、状态和安全错误码，使成功与失败调用均可审计和按运行 ID 查询，同时保持现有同步调用方式。

## 已确认决策

- 保存原始用户输入和最终模型输出。
- 不保存思维链、请求头、API 密钥、数据库/SDK 原始异常。
- 使用 `running → completed|failed` 状态机，每次状态变化使用独立短事务提交。
- 失败 HTTP 响应增加顶层 `run_id`，其余错误码、消息和状态码保持兼容。
- 兼容入口的 `agent_id` 为 `NULL`。

## 数据模型

新表 `agent_runs`：

| 列 | 类型 | 约束 |
| --- | --- | --- |
| `id` | UUID | 主键 |
| `agent_id` | UUID | 可空，外键 `agents.id`，删除 Agent 时限制删除 |
| `input` | TEXT | 非空 |
| `output` | TEXT | 可空，仅成功时有值 |
| `status` | VARCHAR(20) | 非空，仅 `running/completed/failed` |
| `error_code` | VARCHAR(100) | 可空，仅失败时有值 |
| `created_at` | TIMESTAMP WITH TIME ZONE | 非空 |
| `completed_at` | TIMESTAMP WITH TIME ZONE | 可空 |

状态不变量：`running` 不含 output/error/completed_at；`completed` 包含 output/completed_at 且无 error；`failed` 包含 error_code/completed_at 且无 output。领域对象不可变，由状态转换返回新值。

## 组件边界

### `AgentRunRepository`

```python
def add(self, run: PersistedAgentRun) -> None: ...
def get(self, run_id: str) -> PersistedAgentRun | None: ...
def update(self, run: PersistedAgentRun) -> None: ...
```

SQLAlchemy 实现负责 ORM 映射，但不决定事务边界。

### `AgentRunRecorder`

录制器为运行编排提供短事务方法：

```python
start(agent_id: str | None, input: str) -> PersistedAgentRun
complete(run_id: str, output: str) -> PersistedAgentRun
fail(run_id: str, error_code: str) -> PersistedAgentRun
get(run_id: str) -> PersistedAgentRun
```

每个方法创建独立 Session，成功提交，异常回滚并关闭。`start` 提交完成后才允许调用 DeepSeek，确保后续失败不会丢失初始记录。

### 运行编排

配置 Agent 入口先确认 Agent 存在，再调用 `start(agent_id, message)`。兼容入口调用 `start(None, message)`。随后执行 DeepSeek：

1. 成功：`complete(run_id, output)`，返回原有成功响应。
2. 已分类 DeepSeek 异常：`fail(run_id, stable_error_code)`，将 `run_id` 绑定到异常并重新抛出。
3. 数据库录制失败：不调用或停止调用 DeepSeek，返回现有安全数据库错误。

异常绑定不得改变 SDK/数据库原始异常文本的保密边界。

## HTTP API

### 查询运行

`GET /api/v1/agent-runs/{run_id}`：

```json
{
  "id": "...",
  "agent_id": "...",
  "input": "分析本月异常",
  "output": "发现华东区域异常",
  "status": "completed",
  "error_code": null,
  "created_at": "2026-08-20T09:30:00Z",
  "completed_at": "2026-08-20T09:30:02Z"
}
```

合法 UUID 不存在时返回 `404/agent_run_not_found`；非法 UUID 返回 `422`。

### 成功运行

两个现有 POST 端点继续返回 `201` 和现有 `run_id/status/output`，其中 `run_id` 与持久化记录 ID 完全相同。

### 失败运行

DeepSeek 失败响应在现有错误体上增加顶层 `run_id`：

```json
{
  "run_id": "...",
  "error": {"code": "deepseek_timeout", "message": "DeepSeek request timed out"}
}
```

数据库在 `start` 前失败时没有运行 ID，错误体保持原样。输入校验失败不创建记录并保持 `422`。

## 迁移与索引

新增 Alembic 版本创建 `agent_runs`、状态检查约束、Agent 外键，并为 `agent_id`、`status`、`created_at` 建索引。downgrade 只删除新表和索引，不影响 `agents`。

## 错误处理

- `AgentRunNotFoundError` → `404/agent_run_not_found`。
- DeepSeek 分类映射保持现有状态码和固定消息，并携带可选 `run_id`。
- 更新不存在或非法状态转换视为数据库/内部录制失败，对外返回安全 `503/database_unavailable`。
- 若失败状态写入本身失败，优先返回数据库不可用，不声称失败记录已持久化。

## 测试策略

- 状态机单元测试覆盖合法转换和拒绝重复/非法转换。
- SQLite 仓储测试覆盖 add/get/update、可空 Agent ID、长文本、跨 Session 可见。
- 录制器测试覆盖每次方法独立提交、异常回滚关闭。
- 编排测试覆盖先 start 后模型调用、成功 complete、分类异常 fail 后重抛及运行 ID 绑定。
- API 测试覆盖查询、404、成功 ID 一致、失败响应 run_id、输入 `422` 不录制。
- Alembic 测试覆盖 upgrade/downgrade、外键、约束和索引；显式 PostgreSQL 测试复用独立 `_test` 数据库。

## 非目标

- 运行列表、分页、搜索和统计
- 重试、取消、异步队列和 Worker
- 流式输出与增量保存
- 脱敏、加密、保留期限和归档策略
- Token 用量、价格和模型响应元数据
- Agent 删除行为与软删除

## 验收标准

- 成功与 DeepSeek 失败运行均可通过同一 `run_id` 查询。
- `running` 在模型调用前独立提交；最终状态独立提交。
- 两个现有运行入口保持成功兼容，失败仅增加 `run_id`。
- 输入校验失败不创建记录。
- 数据库及上游敏感信息不进入记录或响应。
- Alembic、默认测试、可选 PostgreSQL 测试、Ruff 和 OpenAPI 检查通过。
