# API Key 鉴权实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 使用环境变量中的单一平台 API Key 保护全部 `/api/v1` 业务接口，同时保持健康检查和 API 文档公开。

**Architecture:** 在独立 `auth.py` 中实现惰性配置、HTTP Bearer 提取、常量时间比较和安全异常映射；`main.py` 在注册两个业务路由时统一挂载鉴权依赖。业务服务、仓储与 DeepSeek 适配器不接触凭证，现有接口测试通过共享鉴权 fixture 保持聚焦。

**Tech Stack:** Python 3.11+、FastAPI HTTPBearer、secrets、pytest、Ruff

## Global Constraints

- 仅使用环境变量 `PLATFORM_API_KEY`，不增加用户表、多密钥、JWT、OAuth 或 RBAC。
- `/api/v1/agent-runs` 和 `/api/v1/agents` 路由族全部要求 Bearer 鉴权。
- `/health`、`/docs` 和 `/openapi.json` 保持公开。
- 服务端未配置密钥返回 `503/auth_not_configured`。
- 缺失、格式错误、空白或错误的客户端凭证统一返回 `401/invalid_api_key`，并携带 `WWW-Authenticate: Bearer`。
- 使用 `secrets.compare_digest` 比较密钥；错误、日志和持久化数据不得包含凭证。
- 鉴权失败不得创建数据库 Session、调用 DeepSeek 或写入运行记录。
- 鉴权通过后的现有成功和错误响应契约保持不变。

---

## 文件结构

- 新建 `src/chint_ai_platform/auth.py`：鉴权配置、HTTP Bearer 安全方案、依赖函数和异常处理器。
- 修改 `src/chint_ai_platform/main.py`：为两个业务路由统一挂载鉴权依赖并注册异常处理器。
- 新建 `tests/test_auth.py`：鉴权边界单元测试。
- 新建 `tests/conftest.py`：为现有 API 测试提供统一的测试密钥、合法请求头和客户端 fixture。
- 新建 `tests/test_auth_api.py`：路由保护、公开端点、短路行为及 OpenAPI 集成测试。
- 修改 `tests/test_agent_runs_api.py`、`tests/test_agents_api.py`：通过共享 fixture 为非鉴权测试提供合法凭证。
- 修改 `.env.example`、`README.md`：记录配置项和带 Bearer 头的调用示例。

---

### Task 1: 鉴权配置与凭证校验边界

**Files:**
- Create: `src/chint_ai_platform/auth.py`
- Create: `tests/test_auth.py`

**Interfaces:**
- Consumes: `os.environ`、`fastapi.security.HTTPAuthorizationCredentials`、`secrets.compare_digest`。
- Produces: `AuthenticationNotConfiguredError`、`InvalidApiKeyError`、`get_platform_api_key() -> str`、`validate_api_key(credentials: HTTPAuthorizationCredentials | None) -> None`、`bearer_scheme`。

- [ ] **Step 1: 编写配置缺失与凭证校验失败测试**

```python
import pytest
from fastapi.security import HTTPAuthorizationCredentials

import chint_ai_platform.auth as auth_module
from chint_ai_platform.auth import (
    AuthenticationNotConfiguredError,
    InvalidApiKeyError,
    get_platform_api_key,
    validate_api_key,
)


@pytest.mark.parametrize("value", [None, "", "   "])
def test_platform_api_key_must_be_configured(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("PLATFORM_API_KEY", raising=False)
    else:
        monkeypatch.setenv("PLATFORM_API_KEY", value)
    with pytest.raises(AuthenticationNotConfiguredError):
        get_platform_api_key()


@pytest.mark.parametrize("credentials", [None, HTTPAuthorizationCredentials(scheme="Basic", credentials="secret"), HTTPAuthorizationCredentials(scheme="Bearer", credentials="wrong")])
def test_validate_api_key_rejects_all_invalid_credentials(monkeypatch, credentials):
    monkeypatch.setenv("PLATFORM_API_KEY", "test-platform-key")
    with pytest.raises(InvalidApiKeyError):
        validate_api_key(credentials)
```

- [ ] **Step 2: 运行测试确认红灯**

Run: `pytest tests/test_auth.py -v`

Expected: FAIL，原因是 `chint_ai_platform.auth` 尚不存在。

- [ ] **Step 3: 实现最小鉴权边界**

```python
"""Platform API key authentication boundary."""

import os
import secrets

from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


class AuthenticationNotConfiguredError(RuntimeError):
    """Raised when the server has no platform API key."""


class InvalidApiKeyError(PermissionError):
    """Raised when a client does not present the configured key."""


bearer_scheme = HTTPBearer(auto_error=False)


def get_platform_api_key() -> str:
    api_key = os.environ.get("PLATFORM_API_KEY", "").strip()
    if not api_key:
        raise AuthenticationNotConfiguredError("API authentication is not configured")
    return api_key


def validate_api_key(credentials: HTTPAuthorizationCredentials | None) -> None:
    configured_key = get_platform_api_key()
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise InvalidApiKeyError("Invalid API key")
    if not credentials.credentials or not secrets.compare_digest(
        credentials.credentials, configured_key
    ):
        raise InvalidApiKeyError("Invalid API key")
```

- [ ] **Step 4: 增加成功路径与常量时间比较调用测试**

```python
def test_validate_api_key_uses_compare_digest(monkeypatch):
    compared = []
    monkeypatch.setenv("PLATFORM_API_KEY", "test-platform-key")
    monkeypatch.setattr(
        auth_module.secrets,
        "compare_digest",
        lambda presented, configured: compared.append((presented, configured)) or True,
    )
    validate_api_key(HTTPAuthorizationCredentials(scheme="Bearer", credentials="client-key"))
    assert compared == [("client-key", "test-platform-key")]
```

- [ ] **Step 5: 运行单元测试并提交**

Run: `pytest tests/test_auth.py -v`

Expected: PASS。

```powershell
git add src/chint_ai_platform/auth.py tests/test_auth.py
git commit -m "feat: add API key authentication boundary"
```

---

### Task 2: FastAPI 依赖与安全错误响应

**Files:**
- Modify: `src/chint_ai_platform/auth.py`
- Modify: `tests/test_auth.py`

**Interfaces:**
- Consumes: Task 1 的 `validate_api_key`、`bearer_scheme` 和两个边界异常。
- Produces: `require_api_key(credentials: Annotated[HTTPAuthorizationCredentials | None, Security(bearer_scheme)]) -> None`、`register_auth_exception_handlers(application: FastAPI) -> None`。

- [ ] **Step 1: 编写依赖委托和安全异常处理测试**

```python
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from chint_ai_platform.auth import register_auth_exception_handlers, require_api_key


def make_protected_app() -> FastAPI:
    application = FastAPI()
    register_auth_exception_handlers(application)

    @application.get("/protected", dependencies=[Depends(require_api_key)])
    def protected() -> dict[str, bool]:
        return {"ok": True}

    return application


def test_missing_server_key_returns_safe_503(monkeypatch):
    monkeypatch.delenv("PLATFORM_API_KEY", raising=False)
    response = TestClient(make_protected_app()).get("/protected")
    assert response.status_code == 503
    assert response.json() == {"error": {"code": "auth_not_configured", "message": "API authentication is not configured"}}


def test_invalid_client_key_returns_uniform_401(monkeypatch):
    monkeypatch.setenv("PLATFORM_API_KEY", "test-platform-key")
    response = TestClient(make_protected_app()).get("/protected")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {"error": {"code": "invalid_api_key", "message": "Invalid API key"}}
```

- [ ] **Step 2: 运行测试确认红灯**

Run: `pytest tests/test_auth.py -v`

Expected: FAIL，原因是依赖函数和异常处理器尚不存在。

- [ ] **Step 3: 实现依赖函数和处理器**

```python
from typing import Annotated

from fastapi import FastAPI, Request, Security, status
from fastapi.responses import JSONResponse


def require_api_key(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(bearer_scheme),
    ],
) -> None:
    validate_api_key(credentials)


def register_auth_exception_handlers(application: FastAPI) -> None:
    async def handle_not_configured(
        request: Request,
        error: AuthenticationNotConfiguredError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": {"code": "auth_not_configured", "message": "API authentication is not configured"}},
        )

    async def handle_invalid_key(request: Request, error: InvalidApiKeyError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Bearer"},
            content={"error": {"code": "invalid_api_key", "message": "Invalid API key"}},
        )

    application.add_exception_handler(AuthenticationNotConfiguredError, handle_not_configured)
    application.add_exception_handler(InvalidApiKeyError, handle_invalid_key)
```

- [ ] **Step 4: 增加格式错误、错误方案、空白和错误密钥的参数化测试**

```python
@pytest.mark.parametrize(
    "authorization",
    [None, "", "Basic secret", "Bearer", "Bearer wrong-key"],
)
def test_all_invalid_authorization_headers_are_indistinguishable(monkeypatch, authorization):
    monkeypatch.setenv("PLATFORM_API_KEY", "test-platform-key")
    headers = {} if authorization is None else {"Authorization": authorization}
    response = TestClient(make_protected_app()).get("/protected", headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_api_key"
```

- [ ] **Step 5: 运行测试并提交**

Run: `pytest tests/test_auth.py -v`

Expected: PASS。

```powershell
git add src/chint_ai_platform/auth.py tests/test_auth.py
git commit -m "feat: expose API key FastAPI dependency"
```

---

### Task 3: 业务路由保护与 OpenAPI 契约

**Files:**
- Modify: `src/chint_ai_platform/main.py`
- Create: `tests/test_auth_api.py`

**Interfaces:**
- Consumes: Task 2 的 `require_api_key` 和 `register_auth_exception_handlers`。
- Produces: 两个受保护路由族、三个公开端点及 OpenAPI HTTP Bearer 声明。

- [ ] **Step 1: 编写路由保护和公开端点测试**

```python
import pytest
from fastapi.testclient import TestClient

from chint_ai_platform.main import create_app


@pytest.mark.parametrize(
    ("method", "path"),
    [("post", "/api/v1/agent-runs"), ("post", "/api/v1/agents")],
)
def test_business_routes_require_api_key(monkeypatch, method, path):
    monkeypatch.setenv("PLATFORM_API_KEY", "test-platform-key")
    response = getattr(TestClient(create_app()), method)(path, json={})
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_api_key"


@pytest.mark.parametrize("path", ["/health", "/docs", "/openapi.json"])
def test_operational_and_documentation_routes_are_public(monkeypatch, path):
    monkeypatch.delenv("PLATFORM_API_KEY", raising=False)
    assert TestClient(create_app()).get(path).status_code == 200
```

- [ ] **Step 2: 运行测试确认红灯**

Run: `pytest tests/test_auth_api.py -v`

Expected: FAIL，业务路由当前进入现有参数校验并返回 422。

- [ ] **Step 3: 在应用装配点统一挂载依赖**

```python
from fastapi import Depends, FastAPI

from chint_ai_platform.auth import register_auth_exception_handlers, require_api_key


def create_app() -> FastAPI:
    application = FastAPI(title="CHINT Enterprise AI Agent Platform", version="0.1.0")
    authentication = [Depends(require_api_key)]
    application.include_router(agent_runs_router, dependencies=authentication)
    application.include_router(agents_router, dependencies=authentication)
    register_auth_exception_handlers(application)
    register_deepseek_exception_handlers(application)
    register_agent_exception_handlers(application)
    # 保留现有 health 路由定义
    return application
```

- [ ] **Step 4: 编写 OpenAPI 安全声明测试**

```python
def test_openapi_declares_bearer_security_only_for_business_routes():
    schema = create_app().openapi()
    schemes = schema["components"]["securitySchemes"]
    bearer_name = next(
        name
        for name, value in schemes.items()
        if value["type"] == "http" and value["scheme"] == "bearer"
    )
    assert schema["paths"]["/api/v1/agent-runs"]["post"]["security"] == [{bearer_name: []}]
    assert schema["paths"]["/api/v1/agents"]["post"]["security"] == [{bearer_name: []}]
    assert "security" not in schema["paths"]["/health"]["get"]
```

- [ ] **Step 5: 编写鉴权失败短路业务依赖测试**

```python
def test_authentication_failure_does_not_call_agent_run_service(monkeypatch):
    called = False

    def forbidden_service():
        nonlocal called
        called = True
        raise AssertionError("service must not be resolved")

    monkeypatch.setenv("PLATFORM_API_KEY", "test-platform-key")
    application = create_app()
    application.dependency_overrides[get_agent_run_service] = forbidden_service
    response = TestClient(application).post(
        "/api/v1/agent-runs",
        json={"message": "分析异常"},
    )
    assert response.status_code == 401
    assert called is False
```

- [ ] **Step 6: 运行集成测试并提交**

Run: `pytest tests/test_auth_api.py -v`

Expected: PASS。

```powershell
git add src/chint_ai_platform/main.py tests/test_auth_api.py
git commit -m "feat: protect business API routes"
```

---

### Task 4: 迁移现有 API 测试到合法凭证

**Files:**
- Create: `tests/conftest.py`
- Modify: `tests/test_agent_runs_api.py`
- Modify: `tests/test_agents_api.py`

**Interfaces:**
- Consumes: 受保护的 `create_app()`。
- Produces: 自动配置 `PLATFORM_API_KEY` 的 `configured_api_key` fixture、合法请求头 `auth_headers` fixture；现有 API 行为继续由原测试覆盖。

- [ ] **Step 1: 运行现有 API 测试确认因鉴权失败而红灯**

Run: `pytest tests/test_agent_runs_api.py tests/test_agents_api.py -q`

Expected: 多个原本断言 2xx、4xx、503 的测试实际收到 `401/invalid_api_key`。

- [ ] **Step 2: 新增共享 fixture**

```python
import pytest


@pytest.fixture
def configured_api_key(monkeypatch: pytest.MonkeyPatch) -> str:
    api_key = "test-platform-api-key"
    monkeypatch.setenv("PLATFORM_API_KEY", api_key)
    return api_key


@pytest.fixture
def auth_headers(configured_api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {configured_api_key}"}
```

- [ ] **Step 3: 为原有 API 测试显式注入合法请求头**

对 `tests/test_agent_runs_api.py` 和 `tests/test_agents_api.py` 中所有测试鉴权之后行为的请求：

```python
def test_existing_behavior(auth_headers: dict[str, str]) -> None:
    response = TestClient(create_app()).post(
        "/api/v1/agent-runs",
        headers=auth_headers,
        json={"message": "分析异常"},
    )
    # 保留原有断言
```

错误映射、空消息 422、未知 Agent 404、数据库 503、DeepSeek 错误和运行记录查询测试均必须
携带 `auth_headers`，确保它们仍验证原有业务边界，而不是鉴权边界。

- [ ] **Step 4: 运行全部 API 与健康检查测试**

Run: `pytest tests/test_auth.py tests/test_auth_api.py tests/test_agent_runs_api.py tests/test_agents_api.py tests/test_health.py -q`

Expected: PASS。

- [ ] **Step 5: 提交测试迁移**

```powershell
git add tests/conftest.py tests/test_agent_runs_api.py tests/test_agents_api.py
git commit -m "test: authenticate existing API scenarios"
```

---

### Task 5: 配置与使用文档

**Files:**
- Modify: `.env.example`
- Modify: `README.md`

**Interfaces:**
- Consumes: `PLATFORM_API_KEY` 和 `Authorization: Bearer <key>` 契约。
- Produces: 可复制的本地配置与 PowerShell 请求示例。

- [ ] **Step 1: 更新环境变量示例**

在 `.env.example` 首行附近增加占位值：

```dotenv
PLATFORM_API_KEY=replace-with-a-long-random-platform-key
```

- [ ] **Step 2: 更新 README 本地运行和请求示例**

在启动命令中增加：

```powershell
$env:PLATFORM_API_KEY = "替换为长随机平台密钥"
$headers = @{ Authorization = "Bearer $env:PLATFORM_API_KEY" }
```

所有 `/api/v1` 的 `Invoke-RestMethod` 示例增加：

```powershell
-Headers $headers `
```

明确说明 `/health`、`/docs`、`/openapi.json` 无需鉴权；服务端未配置密钥返回 503，客户端
无效凭证返回 401。

- [ ] **Step 3: 运行文档与敏感信息检查**

Run: `rg -n "PLATFORM_API_KEY|Authorization" README.md .env.example`

Expected: 只出现配置名称、占位值和示例变量，不出现真实密钥。

- [ ] **Step 4: 提交文档**

```powershell
git add .env.example README.md
git commit -m "docs: document API key authentication"
```

---

### Task 6: 全量验证与交付

**Files:**
- Verify: `src/chint_ai_platform/auth.py`
- Verify: `src/chint_ai_platform/main.py`
- Verify: `tests/`
- Verify: `.env.example`
- Verify: `README.md`

**Interfaces:**
- Consumes: Tasks 1–5 的全部实现。
- Produces: 通过复审并推送的 `feature/api-key-authentication` 分支。

- [ ] **Step 1: 运行完整测试与静态检查**

Run: `pytest -q`

Expected: 全部自动测试通过，仅允许显式 PostgreSQL 集成测试因未配置 `_test` 数据库而跳过。

Run: `ruff check .`

Expected: `All checks passed!`

- [ ] **Step 2: 验证 OpenAPI 与差异完整性**

Run: `python -c "from chint_ai_platform.main import create_app; s=create_app().openapi(); assert s['components']['securitySchemes']; assert 'security' not in s['paths']['/health']['get']; print('OpenAPI auth OK')"`

Expected: `OpenAPI auth OK`。

Run: `git diff --check`

Expected: 无空白错误。

- [ ] **Step 3: 扫描敏感信息**

Run: `rg -n --hidden -g '!.git/**' -g '!.pytest-tmp/**' -g '!*.db' 'sk-[A-Za-z0-9_-]{10,}' .`

Expected: 无匹配。

- [ ] **Step 4: 请求独立代码审查并修复所有 Critical、Important 和 Minor 问题**

审查重点：鉴权覆盖是否可遗漏、缺失配置与无效凭证优先级、常量时间比较、OpenAPI 安全
声明、错误体是否泄露凭证、未认证请求是否触发数据库或 DeepSeek。

- [ ] **Step 5: 最终验证并推送功能分支**

Run: `pytest -q && ruff check . && git status --short --branch`

Expected: 测试和 Ruff 通过，工作树仅包含计划内交付改动或已经干净。

```powershell
git push -u origin feature/api-key-authentication
```

推送后确认本地分支与 `origin/feature/api-key-authentication` 同步。不要合并或推送 `main`；
该操作必须等待用户明确批准。
