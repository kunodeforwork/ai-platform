# DeepSeek V4 Flash Executor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the default echo executor with a production DeepSeek V4 Flash adapter while preserving the existing Agent run success contract and adding safe upstream error responses.

**Architecture:** A frozen settings object reads environment configuration, while `DeepSeekAgentExecutor` adapts the OpenAI-compatible SDK to the existing synchronous `AgentExecutor` protocol. Executor-specific exceptions cross the application boundary and are converted to stable HTTP error envelopes by the API layer.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, OpenAI Python SDK, pytest, Ruff

## Global Constraints

- Default model is exactly `deepseek-v4-flash`.
- Every model request sends `stream=False` and `extra_body={"thinking": {"type": "disabled"}}`.
- API keys are read only from `DEEPSEEK_API_KEY` and never included in responses, logs, fixtures, or tracked files.
- Automated tests must not access the network or require a real API key.
- Do not add conversations, streaming, tools, knowledge retrieval, retries, persistence, authentication, or tenancy.

---

### Task 1: Environment-backed DeepSeek settings

**Files:**
- Create: `src/chint_ai_platform/settings.py`
- Create: `tests/test_settings.py`
- Create: `.env.example`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: optional `Mapping[str, str]`
- Produces: `DeepSeekSettings.from_environment(environ: Mapping[str, str] | None = None) -> DeepSeekSettings`

- [ ] **Step 1: Write failing settings tests**

```python
def test_settings_use_deepseek_defaults():
    settings = DeepSeekSettings.from_environment({"DEEPSEEK_API_KEY": "secret"})
    assert settings.api_key == "secret"
    assert settings.base_url == "https://api.deepseek.com"
    assert settings.model == "deepseek-v4-flash"

def test_settings_allow_endpoint_and_model_overrides():
    settings = DeepSeekSettings.from_environment({
        "DEEPSEEK_API_KEY": "secret",
        "DEEPSEEK_BASE_URL": "https://gateway.example/v1",
        "DEEPSEEK_MODEL": "deployment-name",
    })
    assert settings.base_url == "https://gateway.example/v1"
    assert settings.model == "deployment-name"

def test_settings_reject_missing_api_key():
    with pytest.raises(DeepSeekNotConfiguredError):
        DeepSeekSettings.from_environment({})
```

- [ ] **Step 2: Run tests and verify missing-module failure**

Run: `pytest tests/test_settings.py -v`
Expected: FAIL because `chint_ai_platform.settings` does not exist.

- [ ] **Step 3: Implement immutable settings and configuration exception**

Use a frozen dataclass, accept an injected mapping for deterministic tests, and fall back to `os.environ` only when no mapping is supplied. Reject missing or blank keys.

- [ ] **Step 4: Add safe environment templates**

Add `DEEPSEEK_API_KEY=replace-with-your-key`, the two documented defaults, and `.env` to `.gitignore`.

- [ ] **Step 5: Run settings tests**

Run: `pytest tests/test_settings.py -v`
Expected: PASS.

### Task 2: DeepSeek SDK executor

**Files:**
- Create: `src/chint_ai_platform/deepseek.py`
- Create: `tests/test_deepseek_executor.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: `DeepSeekSettings` and an OpenAI-compatible client exposing `chat.completions.create(...)`
- Produces: `DeepSeekAgentExecutor.execute(message: str) -> str`, plus `DeepSeekTimeoutError`, `DeepSeekRateLimitedError`, `DeepSeekAuthenticationError`, and `DeepSeekUpstreamError`

- [ ] **Step 1: Write a failing request-contract test**

Create a hand-written recording client returning a complete response-shaped object. Assert the executor returns the first message content and records exactly:

```python
{
    "model": "deepseek-v4-flash",
    "messages": [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": "分析本月销售异常"},
    ],
    "stream": False,
    "extra_body": {"thinking": {"type": "disabled"}},
}
```

- [ ] **Step 2: Run the request-contract test and verify missing-module failure**

Run: `pytest tests/test_deepseek_executor.py::test_executor_sends_non_thinking_v4_flash_request -v`
Expected: FAIL because `chint_ai_platform.deepseek` does not exist.

- [ ] **Step 3: Add the OpenAI SDK dependency and minimal executor**

Add `openai>=1.99,<3` to project dependencies. Implement the exact synchronous request and content extraction without retries or additional parameters.

- [ ] **Step 4: Run the request-contract test**

Run the same targeted command.
Expected: PASS.

- [ ] **Step 5: Write failing invalid-response and SDK-error translation tests**

Cover no choices, blank content, `APITimeoutError`, `RateLimitError`, `AuthenticationError`, `APIConnectionError`, and a generic `APIStatusError`. Construct SDK exceptions with minimal real `httpx.Request`/`Response` objects and assert only the corresponding executor exception type.

- [ ] **Step 6: Run the new tests and verify the expected raw exceptions or invalid return values**

Run: `pytest tests/test_deepseek_executor.py -v`
Expected: FAIL until each upstream branch is translated.

- [ ] **Step 7: Implement minimal safe exception translation**

Translate timeout, rate limit, authentication, and remaining OpenAI/network/invalid-response failures. Use fixed messages and chain the original exception without exposing it to callers.

- [ ] **Step 8: Run executor tests**

Run: `pytest tests/test_deepseek_executor.py -v`
Expected: PASS.

### Task 3: HTTP error envelope

**Files:**
- Modify: `src/chint_ai_platform/api.py`
- Modify: `tests/test_agent_runs_api.py`

**Interfaces:**
- Consumes: DeepSeek executor exception types
- Produces: `ErrorResponse(error: ErrorDetail)` and the status/code mappings in the approved design

- [ ] **Step 1: Write failing parameterized API error tests**

Override `get_agent_run_service` with a service that raises one configured exception. For each case assert the exact status and body:

```python
{"error": {"code": expected_code, "message": expected_message}}
```

Cover not configured (`503`), timeout (`504`), rate limited (`503`), authentication (`502`), and generic upstream (`502`).

- [ ] **Step 2: Run the API tests and verify uncaught exceptions**

Run: `pytest tests/test_agent_runs_api.py -v`
Expected: FAIL because executor exceptions are not mapped.

- [ ] **Step 3: Implement a focused exception-to-response mapping**

Catch only the five declared boundary exceptions around `service.run`, and return `JSONResponse` with fixed status, code, and message. Do not serialize original exception text.

- [ ] **Step 4: Run API tests**

Run: `pytest tests/test_agent_runs_api.py -v`
Expected: PASS.

### Task 4: Default production wiring

**Files:**
- Modify: `src/chint_ai_platform/api.py`
- Modify: `tests/test_agent_runs_api.py`

**Interfaces:**
- Consumes: `DeepSeekSettings.from_environment()`, `OpenAI(api_key=..., base_url=...)`, and `DeepSeekAgentExecutor`
- Produces: default `get_agent_run_service() -> AgentRunService` backed by DeepSeek

- [ ] **Step 1: Write a failing no-key integration-boundary test**

Clear `DEEPSEEK_API_KEY`, clear the cached provider, call the real endpoint without overriding dependencies, and assert `503/deepseek_not_configured`; restore provider cache isolation after the test.

- [ ] **Step 2: Run the targeted test and verify it fails against the echo default**

Run the new test by node id.
Expected: FAIL with `201` because the default still uses `EchoAgentExecutor`.

- [ ] **Step 3: Replace echo wiring with lazy DeepSeek construction**

Build settings and the OpenAI client only when the dependency is first requested. Keep `lru_cache` and allow configuration errors to cross into the existing HTTP mapping.

- [ ] **Step 4: Run the targeted test and full suite**

Run: `pytest -v`
Expected: all tests PASS without network access.

### Task 5: Documentation and final verification

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: the environment and endpoint contracts above
- Produces: safe setup and manual connectivity instructions

- [ ] **Step 1: Document DeepSeek configuration and execution**

Explain copying `.env.example`, setting `DEEPSEEK_API_KEY` in the shell, starting Uvicorn, and issuing the existing sample request. State that automated tests never call DeepSeek.

- [ ] **Step 2: Run complete verification**

Run: `pytest -v`, `ruff check .`, and an OpenAPI smoke check.
Expected: all commands pass; tracked-file search contains no credential value.

- [ ] **Step 3: Review against the approved specification**

Confirm every error branch, configuration default, request parameter, acceptance criterion, and non-goal.

- [ ] **Step 4: Commit the complete slice**

```bash
git add .env.example .gitignore README.md pyproject.toml src tests docs/superpowers/plans/2026-08-20-deepseek-executor.md
git commit -m "feat: integrate DeepSeek V4 Flash executor"
```
