# Agent Run Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist every successful or failed Agent execution and expose it by run ID without breaking existing synchronous endpoints.

**Architecture:** An immutable run state machine is stored through an `AgentRunRepository`. `SqlAlchemyAgentRunRecorder` owns one short transaction per start/complete/fail operation, while orchestration records `running` before DeepSeek and binds the persisted ID to safe upstream failures.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.x, Alembic, PostgreSQL 16, pytest

## Global Constraints

- Never persist reasoning content, secrets, headers, SQL, or raw exceptions.
- Input validation creates no run record.
- `running` is committed before model execution; terminal state is committed separately.
- Existing success contracts remain unchanged; DeepSeek errors only add top-level `run_id`.

---

### Task 1: Run domain state machine

**Files:** `src/chint_ai_platform/agent_runs.py`, `tests/test_agent_run_service.py`

- [ ] Write failing tests for running creation, complete/fail transitions, timestamps, and rejected illegal transitions.
- [ ] Implement `PersistedAgentRun`, status literals, `AgentRunNotFoundError`, and pure transition methods.
- [ ] Run targeted tests.

### Task 2: ORM and repository

**Files:** `src/chint_ai_platform/persistence.py`, `tests/test_run_persistence.py`

- [ ] Write failing SQLite tests for add/get/update, nullable Agent ID, text fields, UUID/time mapping, and missing IDs.
- [ ] Implement `AgentRunRow` and `SqlAlchemyAgentRunRepository` without owning transaction boundaries.
- [ ] Run repository tests.

### Task 3: Short-transaction recorder

**Files:** `src/chint_ai_platform/run_recording.py`, `tests/test_run_recording.py`

- [ ] Write failing tests proving each start/complete/fail opens, commits, and closes its own Session and rolls back on failure.
- [ ] Implement recorder with injected session factory, repository factory, UUID and clock.
- [ ] Translate SQLAlchemy/invalid-state failures to the existing safe database boundary.
- [ ] Run recorder tests.

### Task 4: Execution orchestration

**Files:** `src/chint_ai_platform/agent_runs.py`, `src/chint_ai_platform/agents.py`, associated tests

- [ ] Write failing tests proving start precedes executor, success completes, classified DeepSeek failure records stable code then rethrows with run ID.
- [ ] Implement default and configured orchestration while preserving Agent lookup ordering.
- [ ] Run service tests.

### Task 5: HTTP query and error run ID

**Files:** `src/chint_ai_platform/api.py`, `src/chint_ai_platform/agents_api.py`, API tests

- [ ] Write failing tests for GET run, invalid/missing ID, successful ID consistency, failed response run ID, and 422 no-record behavior.
- [ ] Add request-scoped dependencies, response model, GET route, not-found mapping, and optional error `run_id`.
- [ ] Run API tests and full regression suite.

### Task 6: Alembic migration and PostgreSQL integration

**Files:** `alembic/versions/20260820_02_create_agent_runs.py`, migration/integration tests

- [ ] Write failing migration tests for table, FK, check constraint, indexes, downgrade, and metadata parity.
- [ ] Implement migration and extend optional `_test` PostgreSQL round-trip.
- [ ] Run migration tests.

### Task 7: Documentation and delivery

**Files:** `README.md`

- [ ] Document run query and failure audit behavior.
- [ ] Run pytest, Ruff, Alembic heads, OpenAPI, diff, and secret checks.
- [ ] Request independent review and resolve findings.
- [ ] Commit and push `feature/agent-run-persistence`.
