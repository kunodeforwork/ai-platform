# PostgreSQL Agent Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist Agent configurations through a request-scoped SQLAlchemy repository backed by PostgreSQL, with explicit Alembic migrations and safe database errors.

**Architecture:** A lazy request scope owns transaction lifecycle without reading configuration during FastAPI dependency resolution. `SqlAlchemyAgentRepository` maps between ORM rows and the existing immutable domain object; API services remain storage-agnostic.

**Tech Stack:** Python 3.11+, SQLAlchemy 2.x, Alembic, psycopg 3, PostgreSQL 16, FastAPI, pytest

## Global Constraints

- Invalid HTTP input must remain `422` without reading database configuration.
- Production uses PostgreSQL; default automated tests require no Docker or network.
- Migrations are explicit; application startup never creates tables or runs Alembic.
- Never expose database URLs, SQL, driver errors, usernames, or passwords.

---

### Task 1: Database settings and safe errors

**Files:** `src/chint_ai_platform/settings.py`, `tests/test_settings.py`, `.env.example`, `pyproject.toml`

- [ ] Write failing tests for `DatabaseSettings.from_environment`, missing/blank URL, and defaults-free behavior.
- [ ] Implement `DatabaseSettings` and `DatabaseNotConfiguredError`; add SQLAlchemy, Alembic, and psycopg dependencies.
- [ ] Run settings tests.

### Task 2: ORM model and repository

**Files:** `src/chint_ai_platform/persistence.py`, `tests/test_persistence.py`

- [ ] Write failing SQLite repository contract tests for add/get, unknown ID, UUID and timezone mapping across Sessions.
- [ ] Implement declarative `Base`, `AgentRow`, and `SqlAlchemyAgentRepository` using an injected session scope.
- [ ] Run repository tests.

### Task 3: Lazy session and transaction scope

**Files:** `src/chint_ai_platform/persistence.py`, `tests/test_persistence.py`

- [ ] Write failing tests proving no factory call before `session`, single Session per scope, commit, rollback, and close.
- [ ] Implement thread-safe engine/sessionmaker provider and `DatabaseSessionScope` context lifecycle.
- [ ] Translate SQLAlchemy failures to `DatabaseUnavailableError` while preserving domain exceptions.
- [ ] Run persistence tests.

### Task 4: FastAPI production wiring

**Files:** `src/chint_ai_platform/agents_api.py`, `src/chint_ai_platform/main.py`, `tests/test_agents_api.py`

- [ ] Write failing tests for request-scoped service wiring, missing config `503`, database unavailable `503`, and invalid payload remaining `422`.
- [ ] Replace module-level memory graph with lazy scope/repository/service dependencies.
- [ ] Register fixed safe database error envelopes and run Agent API tests.

### Task 5: Alembic and local PostgreSQL

**Files:** `alembic.ini`, `alembic/env.py`, `alembic/versions/*`, `docker-compose.yml`, `tests/test_migrations.py`

- [ ] Write a failing migration metadata/upgrade test.
- [ ] Add explicit initial migration for `agents`, downgrade, and environment-driven Alembic configuration.
- [ ] Add PostgreSQL 16 Compose service with named volume and health check.
- [ ] Run migration tests.

### Task 6: Documentation and delivery

**Files:** `README.md`

- [ ] Document Compose, `DATABASE_URL`, `alembic upgrade head`, API startup, and optional PostgreSQL test URL.
- [ ] Run full pytest, Ruff, Alembic check, OpenAPI smoke, diff and secret checks.
- [ ] Request independent review and resolve findings.
- [ ] Commit and push `feature/postgresql-agent-persistence`.
