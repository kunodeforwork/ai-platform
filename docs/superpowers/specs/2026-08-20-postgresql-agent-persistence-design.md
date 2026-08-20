# PostgreSQL Agent 持久化设计

## 目标

用 SQLAlchemy 2.x 仓储替换生产环境的进程内 Agent 存储，使 Agent 配置可跨服务重启和多进程实例共享，同时保持现有领域服务、HTTP API 和 DeepSeek 运行契约不变。

## 已确认决策

- 生产存储使用 PostgreSQL。
- 数据访问使用 SQLAlchemy 2.x 同步 ORM，与现有同步 FastAPI 和 DeepSeek 链路一致。
- 数据库结构由 Alembic 显式迁移；应用启动不自动建表或执行迁移。
- 日常仓储测试使用临时 SQLite，PostgreSQL 集成测试通过显式环境变量启用。
- 内存仓储保留为测试替身，但生产默认依赖改为 SQLAlchemy 仓储。

## 配置

新增环境变量：

| 变量 | 必填 | 示例 | 用途 |
| --- | --- | --- | --- |
| `DATABASE_URL` | 是 | `postgresql+psycopg://chint:password@localhost:5432/chint_ai` | SQLAlchemy 数据库连接串 |
| `POSTGRES_TEST_DATABASE_URL` | 否 | 独立测试库连接串 | 显式 PostgreSQL 集成测试 |

`DeepSeekSettings` 与数据库配置保持分离。新增不可变 `DatabaseSettings`，缺少或空白 `DATABASE_URL` 时抛出 `DatabaseNotConfiguredError`。应用模块可导入且 `/health` 可响应；首次访问依赖数据库的 Agent 端点时才读取配置和创建引擎。

`.env.example` 只提供占位或本地开发示例，不包含真实密码。`.env` 继续被 Git 忽略。

## 数据模型

表名：`agents`

| 列 | PostgreSQL 类型 | 约束 |
| --- | --- | --- |
| `id` | `UUID` | 主键，不由数据库生成 |
| `name` | `VARCHAR(100)` | 非空 |
| `description` | `VARCHAR(500)` | 非空，默认空字符串 |
| `system_prompt` | `VARCHAR(4000)` | 非空 |
| `created_at` | `TIMESTAMP WITH TIME ZONE` | 非空 |

领域对象继续使用 UUID 字符串和带时区 `datetime`。仓储负责领域对象与 ORM 行之间的双向映射；ORM 类型不得泄漏到服务或 API 层。

## 组件边界

### `DatabaseSettings`

只读取和校验 `DATABASE_URL`，不创建引擎、不连接数据库。

### SQLAlchemy 基础设施

- 声明式 `Base` 和 `AgentRow` 位于独立持久化模块。
- `Engine` 和 `sessionmaker` 由线程安全的惰性提供者构造一次。
- 不在模块导入阶段读取环境变量或建立网络连接。
- SQLAlchemy 默认连接池负责连接复用；本切片不自定义池大小或重试。

### `SqlAlchemyAgentRepository`

构造函数接收一个请求范围的惰性 `DatabaseSessionScope`，实现现有协议：

```python
def add(self, agent: Agent) -> None: ...
def get(self, agent_id: str) -> Agent | None: ...
```

`add` 首次访问 `scope.session` 时才触发配置读取、引擎构造和 Session 创建，然后将对象加入 Session；事务提交由请求会话边界统一负责。`get` 同样按需获取 Session、使用主键查询并映射为领域对象。

### 请求会话与事务

FastAPI 依赖 `get_database_session_scope()` 为每个请求创建轻量、未连接数据库的 `DatabaseSessionScope`：

1. yield scope，此时不读取 `DATABASE_URL`；
2. 仓储首次调用 `scope.session` 时惰性创建该请求独占的 Session；
3. 端点及其服务成功完成后，若 Session 已创建则提交；
4. 发生任何异常时，若 Session 已创建则回滚并重新抛出；
5. 最终关闭已创建的 Session。

Agent 服务和按 ID 运行服务均在同一请求 Session 中使用仓储。全局对象只保存 Engine/sessionmaker，不保存 Session、仓储或 AgentService。

## 依赖装配

当前模块级内存对象图改为请求范围装配：

`get_database_session_scope` → `SqlAlchemyAgentRepository` → `AgentService` → 可选 `ConfiguredAgentRunService`

`get_agent_service(scope=Depends(...))` 每次请求构造轻量服务。`get_configured_agent_run_service` 复用同一请求的 `AgentService`，并组合进程级 DeepSeek `AgentRunService`。所有依赖构造阶段都不得读取数据库配置。

内存实现不再作为默认生产依赖，但继续用于领域单元测试。

## Alembic

- 仓库根目录新增 `alembic.ini` 和 `alembic/`。
- `env.py` 从 `DATABASE_URL` 构造迁移连接，并引用 SQLAlchemy metadata。
- 首个版本创建 `agents` 表及全部约束。
- downgrade 删除 `agents` 表。
- 部署和本地启动流程必须先显式运行 `alembic upgrade head`。
- FastAPI lifespan 不运行 Alembic，也不调用 `metadata.create_all()`。

## 本地 PostgreSQL

新增 `docker-compose.yml`，只包含 PostgreSQL 服务：

- 使用稳定的 PostgreSQL 16 镜像。
- 数据保存在具名 volume。
- 暴露本机 `5432`。
- 健康检查使用 `pg_isready`。
- 用户、密码和数据库名仅作为本地开发默认值，并与 `.env.example` 示例一致。

README 顺序：启动 PostgreSQL → 配置环境 → 安装依赖 → `alembic upgrade head` → 启动 API。

## 错误契约

新增数据库边界异常：

| 场景 | HTTP 状态 | `error.code` | 固定消息 |
| --- | ---: | --- | --- |
| 未配置 `DATABASE_URL` | 503 | `database_not_configured` | `Database is not configured` |
| 连接、查询、提交或回滚相关 SQLAlchemy 错误 | 503 | `database_unavailable` | `Database is unavailable` |

响应不得包含数据库 URL、用户名、密码、SQL、表结构细节或驱动异常正文。Agent 不存在仍返回 `404/agent_not_found`；HTTP 校验仍返回 `422`；DeepSeek 错误契约不变。

为确保无效请求优先返回 `422`，数据库配置和连接必须延迟到通过请求校验、确实执行仓储操作时。不得因缺少数据库配置把空白 Agent 创建或空白运行消息改写为 `503`。

## 测试策略

### 单元与仓储契约测试

- `DatabaseSettings`：配置读取、空白和缺失。
- ORM 映射：全部字段、UUID 和带时区时间。
- `SqlAlchemyAgentRepository`：add/get/未知 ID。
- SQLite 使用临时文件数据库而非纯内存多连接模式，确保提交与新 Session 可见性。
- 事务依赖：成功提交、异常回滚、总是关闭。

### API 测试

- 继续通过 FastAPI 依赖覆盖使用手写服务，保持快速离线。
- 增加默认依赖缺少数据库配置的安全 `503` 测试。
- 增加数据库异常到安全错误体的映射测试。
- 回归验证无效请求优先 `422`、未知 Agent `404`、DeepSeek 错误不变。

### PostgreSQL 集成测试

- 仅当设置 `POSTGRES_TEST_DATABASE_URL` 时运行。
- 在独立测试数据库执行 Alembic upgrade，验证真实 PostgreSQL UUID、时区和跨 Session 持久化。
- 未设置时明确 skip，不影响默认测试套件。
- 测试不得指向或清理非测试数据库；连接串必须明确使用独立测试库名称。

### 迁移测试

- 在临时数据库或离线 SQL 生成模式验证 Alembic 从 base 升级到 head。
- 测试 metadata 与首个迁移包含同一张 `agents` 表和相同关键列。

## 非目标

- Agent 更新、删除、列表、版本和名称唯一性
- 运行记录持久化
- 自动迁移、自动建表和数据库重试
- 异步 SQLAlchemy/asyncpg
- 连接池调优、读写分离和高可用配置
- 用户、租户和权限
- 生产凭据管理平台

## 验收标准

- 通过 HTTP 创建的 Agent 在服务重启或新进程连接同一 PostgreSQL 后仍可查询和运行。
- 生产默认依赖使用 SQLAlchemy 仓储，不再使用进程内仓储。
- 每个请求独立 Session，成功提交，异常回滚并关闭。
- `alembic upgrade head` 可从空 PostgreSQL 数据库创建 `agents` 表。
- 未配置或不可用数据库返回稳定、安全的 `503` 错误结构。
- 无效输入保持 `422`，未知 Agent 保持 `404`，DeepSeek 错误契约保持不变。
- 默认测试无需 Docker 或网络即可通过；显式 PostgreSQL 集成测试可在独立测试库通过。
- `pytest`、`ruff check .`、Alembic 检查和 OpenAPI 冒烟检查全部通过。
