# Minimum Vertical Slice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a locally runnable FastAPI service whose Agent run request crosses HTTP, application-service, and executor boundaries.

**Architecture:** A thin FastAPI router validates and maps HTTP data. `AgentRunService` owns run creation and delegates message processing through an `AgentExecutor` protocol, initially implemented by a deterministic echo executor.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, Uvicorn, pytest, FastAPI TestClient, Ruff

## Global Constraints

- Do not add persistence, authentication, queues, real LLM calls, streaming, Docker, or frontend code.
- Use test-first red-green-refactor for every production behavior.
- Keep the executor replaceable through a typed protocol.

---

### Task 1: FastAPI application and health boundary

**Files:**
- Create: `pyproject.toml`
- Create: `src/chint_ai_platform/__init__.py`
- Create: `src/chint_ai_platform/main.py`
- Test: `tests/test_health.py`

**Interfaces:**
- Consumes: none
- Produces: `create_app() -> FastAPI` and module-level `app`

- [ ] **Step 1: Write the failing health API test**

```python
from fastapi.testclient import TestClient
from chint_ai_platform.main import create_app

def test_health_reports_service_is_up():
    response = TestClient(create_app()).get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 2: Run the test and verify import failure**

Run: `pytest tests/test_health.py -v`
Expected: FAIL because `chint_ai_platform.main` does not exist.

- [ ] **Step 3: Add the minimal package, dependencies, and app factory**

Implement `create_app()` with a `/health` route returning `{"status": "ok"}`, plus `app = create_app()`.

- [ ] **Step 4: Run the test and verify it passes**

Run: `pytest tests/test_health.py -v`
Expected: PASS.

### Task 2: Agent run application service

**Files:**
- Create: `src/chint_ai_platform/agent_runs.py`
- Test: `tests/test_agent_run_service.py`

**Interfaces:**
- Consumes: `AgentExecutor.execute(message: str) -> str`
- Produces: `AgentRunService.run(message: str) -> AgentRun` and `EchoAgentExecutor`

- [ ] **Step 1: Write failing service tests**

Use a hand-written recording executor to verify the exact message is delegated and the returned output, `completed` status, and UUID run identifier are mapped into `AgentRun`.

- [ ] **Step 2: Run the tests and verify missing-symbol failure**

Run: `pytest tests/test_agent_run_service.py -v`
Expected: FAIL because the application-service types do not exist.

- [ ] **Step 3: Implement the minimal protocol, result model, service, and echo executor**

Define `AgentExecutor`, immutable `AgentRun`, `AgentRunService`, and `EchoAgentExecutor`; generate identifiers with UUID4.

- [ ] **Step 4: Run the tests and verify they pass**

Run: `pytest tests/test_agent_run_service.py -v`
Expected: PASS.

### Task 3: Agent run HTTP endpoint

**Files:**
- Create: `src/chint_ai_platform/api.py`
- Modify: `src/chint_ai_platform/main.py`
- Test: `tests/test_agent_runs_api.py`

**Interfaces:**
- Consumes: `AgentRunService.run(message: str) -> AgentRun`
- Produces: `POST /api/v1/agent-runs` with request `{"message": str}` and response `{"run_id": str, "status": "completed", "output": str}`

- [ ] **Step 1: Write failing success and validation API tests**

Assert a valid message returns the exact response contract and a whitespace-only message returns `422`.

- [ ] **Step 2: Run the tests and verify the route is missing**

Run: `pytest tests/test_agent_runs_api.py -v`
Expected: FAIL with `404` for the new endpoint.

- [ ] **Step 3: Implement request/response models, dependency wiring, and router registration**

Use a Pydantic constrained string, a cached default service provider, and include the router from `create_app()`.

- [ ] **Step 4: Run the endpoint tests and full suite**

Run: `pytest -v`
Expected: all tests PASS.

### Task 4: Quality verification and usage documentation

**Files:**
- Create: `README.md`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: module-level `chint_ai_platform.main:app`
- Produces: documented install, test, run, and request commands

- [ ] **Step 1: Add concise local usage documentation**

Document editable installation, `pytest`, Uvicorn startup, endpoint paths, and a sample request/response.

- [ ] **Step 2: Run all automated checks**

Run: `pytest -v` and `ruff check .`
Expected: both commands succeed without warnings or errors.

- [ ] **Step 3: Review the final diff against the design**

Verify every acceptance criterion is implemented and no non-goal entered the slice.
