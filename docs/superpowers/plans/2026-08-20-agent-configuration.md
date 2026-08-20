# Agent Configuration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let callers create and retrieve in-memory Agent configurations, then run DeepSeek with the selected Agent's system prompt while preserving the existing default run endpoint.

**Architecture:** `AgentService` owns creation and lookup through an `AgentRepository` protocol. A locked in-memory repository is process-scoped through FastAPI dependency caching, while a coordinating service joins Agent lookup to the existing run service without coupling HTTP or DeepSeek to storage.

**Tech Stack:** Python 3.11+, FastAPI, dataclasses, threading locks, pytest, Ruff

## Global Constraints

- Keep `POST /api/v1/agent-runs` backward compatible.
- Store Agents only in a process-local, thread-safe repository.
- Pass the selected `system_prompt` exactly to DeepSeek.
- Do not add PostgreSQL, ORM, CRUD beyond create/get, listing, authentication, tenancy, conversations, streaming, tools, or knowledge retrieval.
- Follow red-green-refactor and never access the real DeepSeek API in tests.

---

### Task 1: Agent domain service and repository

**Files:**
- Create: `src/chint_ai_platform/agents.py`
- Create: `tests/test_agents.py`

**Interfaces:**
- Produces: `Agent`, `AgentRepository`, `InMemoryAgentRepository`, `AgentService.create(...)`, `AgentService.get(agent_id)`, `AgentNotFoundError`

- [ ] Write failing tests proving generated UUID4, injected UTC timestamp, normalized fields, add/get behavior, missing lookup, and parallel writes.
- [ ] Run `pytest tests/test_agents.py -v`; verify missing-module failure.
- [ ] Implement immutable `Agent`, repository protocol, locked dictionary repository, service creation and missing lookup.
- [ ] Run `pytest tests/test_agents.py -v`; verify all tests pass.

### Task 2: Dynamic executor system prompt

**Files:**
- Modify: `src/chint_ai_platform/agent_runs.py`
- Modify: `src/chint_ai_platform/deepseek.py`
- Modify: `tests/test_agent_run_service.py`
- Modify: `tests/test_deepseek_executor.py`

**Interfaces:**
- Changes: `AgentExecutor.execute(system_prompt: str, message: str) -> str`
- Changes: `AgentRunService.run(system_prompt: str, message: str) -> AgentRun`
- Produces: `DEFAULT_SYSTEM_PROMPT` used only by the compatibility endpoint

- [ ] Change service tests first to require exact system-prompt and message delegation; run and see signature failures.
- [ ] Minimally update the protocol and run service; rerun service tests.
- [ ] Change DeepSeek request-contract tests first to pass a custom prompt and require it in the system message; run and see signature failures.
- [ ] Update both DeepSeek executors to accept and forward the prompt; rerun executor tests.

### Task 3: Agent application coordinator

**Files:**
- Modify: `src/chint_ai_platform/agents.py`
- Modify: `tests/test_agents.py`

**Interfaces:**
- Consumes: `AgentService.get(agent_id)` and `AgentRunService.run(system_prompt, message)`
- Produces: `ConfiguredAgentRunService.run(agent_id, message) -> AgentRun`

- [ ] Write a failing test with recording collaborators proving lookup and exact prompt/message delegation.
- [ ] Implement the minimal coordinator and rerun `tests/test_agents.py`.

### Task 4: Agent create/get HTTP API

**Files:**
- Create: `src/chint_ai_platform/agents_api.py`
- Modify: `src/chint_ai_platform/main.py`
- Create: `tests/test_agents_api.py`

**Interfaces:**
- Produces: cached `get_agent_service`, `POST /api/v1/agents`, `GET /api/v1/agents/{agent_id}`, and `404/agent_not_found`

- [ ] Write failing API tests for normalized create response, get response, field constraints, invalid UUID, and unknown UUID.
- [ ] Run `pytest tests/test_agents_api.py -v`; verify missing route/module failure.
- [ ] Implement request/response models, cached repository/service wiring, router, and safe not-found handler.
- [ ] Register the router/handler in `create_app`; rerun API tests.

### Task 5: Run by Agent ID and compatibility endpoint

**Files:**
- Modify: `src/chint_ai_platform/agents_api.py`
- Modify: `src/chint_ai_platform/api.py`
- Modify: `tests/test_agents_api.py`
- Modify: `tests/test_agent_runs_api.py`

**Interfaces:**
- Produces: cached `get_configured_agent_run_service`, `POST /api/v1/agents/{agent_id}/runs`
- Preserves: `POST /api/v1/agent-runs` using `DEFAULT_SYSTEM_PROMPT`

- [ ] Write a failing Agent-ID run API test using dependency overrides to prove `agent_id/message` delegation and response mapping.
- [ ] Implement configured-run dependency and route; rerun Agent API tests.
- [ ] Update compatibility tests first to prove `DEFAULT_SYSTEM_PROMPT` and message delegation.
- [ ] Update the compatibility endpoint call and rerun its API tests.
- [ ] Run the full suite.

### Task 6: Documentation, review, and delivery

**Files:**
- Modify: `README.md`

- [ ] Document create/get/run examples and explicitly state process-local data loss/restart behavior.
- [ ] Run `pytest -v`, `ruff check .`, `git diff --check`, and an OpenAPI path smoke check.
- [ ] Request independent code review and resolve all Critical/Important findings.
- [ ] Commit as `feat: add configurable in-memory Agents` and push `feature/agent-configuration`.
