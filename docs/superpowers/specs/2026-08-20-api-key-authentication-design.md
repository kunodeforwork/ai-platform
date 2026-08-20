# API Key 鉴权设计

## 目标

使用一个由部署环境提供的平台 API Key 保护所有业务 API，同时保持健康检查和 API
文档可访问。本切片建立一个小而清晰的安全边界，后续可替换为租户级凭证，而无需让鉴权
逻辑耦合 Agent、持久化或模型执行代码。

## 范围

- 为当前两个 `/api/v1` 路由族启用 HTTP Bearer 鉴权：Agent 配置与 Agent 运行。
- 从进程环境中惰性读取单个 `PLATFORM_API_KEY`。
- 保持 `/health`、`/docs` 和 `/openapi.json` 公开。
- 在 OpenAPI 中声明 Bearer 鉴权方案及受保护操作。
- 鉴权通过后，保持所有现有成功响应和下游错误契约不变。

本切片不包含登录、凭证签发或轮换、多密钥、用户、RBAC、租户隔离、JWT、OAuth、限流，
也不在运行审计记录中保存请求发起者。

## 方案选择

在应用注册两个业务路由时，通过 FastAPI 路由级依赖统一执行鉴权。这种方式集中管理强制
规则，减少单个端点遗漏鉴权的可能，并让 FastAPI 自动生成 OpenAPI 安全声明。

不采用按路径匹配的 HTTP 中间件，因为它会重复维护路由知识；也不采用每个端点单独声明，
因为重复代码较多，新增接口时容易遗漏。

## 组件

### 鉴权边界

新增 `src/chint_ai_platform/auth.py`，职责如下：

- 惰性读取并校验 `PLATFORM_API_KEY`；
- 通过 FastAPI 的 HTTP Bearer 安全方案提取客户端凭证；
- 使用 `secrets.compare_digest` 比较客户端凭证与服务端密钥；
- 抛出不包含凭证内容的稳定边界异常；
- 注册安全的 HTTP 异常映射。

该模块暴露 `require_api_key` 依赖。它不向业务层返回任何值；通过鉴权只表示允许请求继续
执行。Agent 服务、仓储和 DeepSeek 适配器均不会收到 API Key。

### 应用装配

`main.py` 在注册 Agent 配置和 Agent 运行路由时，将 `require_api_key` 作为统一依赖。
健康检查路由位于受保护路由之外。FastAPI 的文档和 OpenAPI 端点也保持默认公开位置。

鉴权配置必须保持惰性读取。缺少服务端鉴权配置时，不影响应用构建、健康检查、文档访问
或 OpenAPI 生成。

## 请求流程

1. 请求进入受保护的 `/api/v1` 路由。
2. 安全依赖将 `Authorization` 请求头解析为 HTTP Bearer 凭证。
3. 服务端密钥缺失或仅包含空白时，鉴权以安全的配置错误终止。
4. 请求头缺失、格式错误、使用其他认证方案、凭证为空或密钥不匹配时，鉴权以统一的无效
   密钥响应终止。
5. 密钥有效时，请求进入现有参数校验和业务处理流程。

鉴权失败不得调用 Agent 服务、创建数据库 Session、调用 DeepSeek 或写入 Agent 运行审计
记录。应用代码不得记录或持久化 Authorization 请求头及其凭证。

## 错误契约

服务端密钥缺失或为空时返回：

```http
HTTP/1.1 503 Service Unavailable
Content-Type: application/json

{"error":{"code":"auth_not_configured","message":"API authentication is not configured"}}
```

任何无效客户端凭证统一返回：

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
Content-Type: application/json

{"error":{"code":"invalid_api_key","message":"Invalid API key"}}
```

401 响应不区分请求头缺失、格式错误、空凭证或密钥错误。503 响应不泄露环境变量内容。
鉴权通过后，现有数据库、Agent、请求校验和 DeepSeek 错误保持不变。

## OpenAPI

生成的 OpenAPI 文档定义 HTTP Bearer 安全方案，并将其应用到两个受保护路由中的所有操作。
`/health` 不声明安全要求。Swagger UI 保持公开，并提供标准的 **Authorize** 按钮用于调用
受保护接口。

## 测试

单元测试覆盖：

- 有效、缺失、空白及错误的环境配置；
- 缺失、格式错误、认证方案错误、空白、错误及正确的客户端凭证；
- 常量时间比较边界确实被调用；
- 稳定异常不包含凭证内容。

API 测试覆盖：

- 两个受保护路由族均拒绝缺失或无效凭证；
- 有效凭证保持代表性的现有成功和错误行为；
- 鉴权失败会短路服务、数据库、DeepSeek 和运行记录写入；
- `/health`、`/docs` 和 `/openapi.json` 保持公开；
- OpenAPI 包含 Bearer 安全方案和受保护操作的安全要求。

现有 API 测试通过共享 fixture 配置平台密钥，并在测试鉴权之后的行为时统一提供有效的
Authorization 请求头。测试不使用真实密钥，也不连接 DeepSeek。

## 交付

在 `.env.example` 和 `README.md` 中记录 `PLATFORM_API_KEY`，并提供带鉴权的 PowerShell
示例。交付前运行完整 pytest、Ruff、OpenAPI 断言、敏感信息扫描和独立代码审查。

合并或推送 `main` 仍需单独获得明确批准。
