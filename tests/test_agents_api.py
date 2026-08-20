from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

import chint_ai_platform.agents_api as agents_api_module
from chint_ai_platform.agent_runs import AgentRun
from chint_ai_platform.agents import Agent, AgentNotFoundError
from chint_ai_platform.main import create_app
from chint_ai_platform.persistence import DatabaseUnavailableError

AGENT_ID = "5b1c53ef-6cd7-4537-81b6-d37ef87c5f69"
CREATED_AT = datetime(2026, 8, 20, 9, 30, tzinfo=UTC)


class RecordingAgentService:
    def __init__(self) -> None:
        self.create_requests: list[tuple[str, str, str]] = []

    def create(self, name: str, description: str, system_prompt: str) -> Agent:
        self.create_requests.append((name, description, system_prompt))
        return Agent(AGENT_ID, name, description, system_prompt, CREATED_AT)

    def get(self, agent_id: str) -> Agent:
        if agent_id != AGENT_ID:
            raise AgentNotFoundError(agent_id)
        return Agent(AGENT_ID, "销售分析助手", "分析异常", "只分析销售数据", CREATED_AT)


class RecordingConfiguredRunService:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str]] = []

    def run(self, agent_id: str, message: str) -> AgentRun:
        self.requests.append((agent_id, message))
        return AgentRun("d6109938-c9ba-4bc0-a20a-27e1b1fceb67", "completed", "分析完成")


class MissingConfiguredRunService:
    def run(self, agent_id: str, message: str) -> AgentRun:
        raise AgentNotFoundError(agent_id)


class UnavailableAgentService(RecordingAgentService):
    def create(self, name: str, description: str, system_prompt: str) -> Agent:
        raise DatabaseUnavailableError("sensitive database detail")


def test_create_agent_normalizes_and_returns_configuration() -> None:
    from chint_ai_platform.agents_api import get_agent_service

    service = RecordingAgentService()
    application = create_app()
    application.dependency_overrides[get_agent_service] = lambda: service

    response = TestClient(application).post(
        "/api/v1/agents",
        json={
            "name": "  销售分析助手  ",
            "description": "  分析异常  ",
            "system_prompt": "  只分析销售数据  ",
        },
    )

    assert response.status_code == 201
    assert service.create_requests == [("销售分析助手", "分析异常", "只分析销售数据")]
    assert response.json() == {
        "id": AGENT_ID,
        "name": "销售分析助手",
        "description": "分析异常",
        "system_prompt": "只分析销售数据",
        "created_at": "2026-08-20T09:30:00Z",
    }


def test_get_agent_returns_configuration() -> None:
    from chint_ai_platform.agents_api import get_agent_service

    application = create_app()
    application.dependency_overrides[get_agent_service] = RecordingAgentService

    response = TestClient(application).get(f"/api/v1/agents/{AGENT_ID}")

    assert response.status_code == 200
    assert response.json()["system_prompt"] == "只分析销售数据"


@pytest.mark.parametrize(
    "payload",
    [
        {"name": " ", "description": "", "system_prompt": "Prompt"},
        {"name": "Agent", "description": "", "system_prompt": "  "},
        {"name": "Agent", "description": "x" * 501, "system_prompt": "Prompt"},
    ],
)
def test_create_agent_rejects_invalid_fields(payload: dict[str, str]) -> None:
    response = TestClient(create_app()).post("/api/v1/agents", json=payload)

    assert response.status_code == 422


def test_get_agent_rejects_invalid_uuid() -> None:
    response = TestClient(create_app()).get("/api/v1/agents/not-a-uuid")

    assert response.status_code == 422


def test_get_agent_returns_safe_not_found_error() -> None:
    from chint_ai_platform.agents_api import get_agent_service

    application = create_app()
    application.dependency_overrides[get_agent_service] = RecordingAgentService

    response = TestClient(application).get(
        "/api/v1/agents/8e52ea3a-f9ec-41b8-9464-e21e4c4ef9e9"
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "agent_not_found", "message": "Agent not found"}
    }


def test_run_agent_delegates_id_and_message() -> None:
    from chint_ai_platform.agents_api import get_configured_agent_run_service

    service = RecordingConfiguredRunService()
    application = create_app()
    application.dependency_overrides[get_configured_agent_run_service] = lambda: service

    response = TestClient(application).post(
        f"/api/v1/agents/{AGENT_ID}/runs",
        json={"message": "分析本月异常"},
    )

    assert response.status_code == 201
    assert service.requests == [(AGENT_ID, "分析本月异常")]
    assert response.json() == {
        "run_id": "d6109938-c9ba-4bc0-a20a-27e1b1fceb67",
        "status": "completed",
        "output": "分析完成",
    }


def test_run_unknown_agent_returns_safe_not_found_error() -> None:
    from chint_ai_platform.agents_api import get_configured_agent_run_service

    application = create_app()
    application.dependency_overrides[
        get_configured_agent_run_service
    ] = MissingConfiguredRunService

    response = TestClient(application).post(
        "/api/v1/agents/8e52ea3a-f9ec-41b8-9464-e21e4c4ef9e9/runs",
        json={"message": "分析异常"},
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "agent_not_found", "message": "Agent not found"}
    }


def test_run_agent_rejects_blank_message_without_calling_service() -> None:
    from chint_ai_platform.agents_api import get_configured_agent_run_service

    service = RecordingConfiguredRunService()
    application = create_app()
    application.dependency_overrides[get_configured_agent_run_service] = lambda: service

    response = TestClient(application).post(
        f"/api/v1/agents/{AGENT_ID}/runs",
        json={"message": "   "},
    )

    assert response.status_code == 422
    assert service.requests == []


def test_default_create_reports_missing_database_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    response = TestClient(create_app(), raise_server_exceptions=False).post(
        "/api/v1/agents",
        json={"name": "Agent", "description": "", "system_prompt": "Prompt"},
    )

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "database_not_configured",
            "message": "Database is not configured",
        }
    }


def test_create_maps_database_failure_to_safe_response() -> None:
    from chint_ai_platform.agents_api import get_agent_service

    application = create_app()
    application.dependency_overrides[get_agent_service] = UnavailableAgentService

    response = TestClient(application, raise_server_exceptions=False).post(
        "/api/v1/agents",
        json={"name": "Agent", "description": "", "system_prompt": "Prompt"},
    )

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "database_unavailable",
            "message": "Database is unavailable",
        }
    }


class RecordingScope:
    def __init__(self) -> None:
        self.commits = 0
        self.rollbacks = 0
        self.closes = 0

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1

    def close(self) -> None:
        self.closes += 1


def test_database_scope_dependency_commits_and_closes(monkeypatch: pytest.MonkeyPatch) -> None:
    scope = RecordingScope()
    monkeypatch.setattr(agents_api_module, "DatabaseSessionScope", lambda factory: scope)
    dependency = agents_api_module.get_database_session_scope()

    assert next(dependency) is scope
    with pytest.raises(StopIteration):
        next(dependency)

    assert (scope.commits, scope.rollbacks, scope.closes) == (1, 0, 1)


def test_database_scope_dependency_rolls_back_and_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scope = RecordingScope()
    monkeypatch.setattr(agents_api_module, "DatabaseSessionScope", lambda factory: scope)
    dependency = agents_api_module.get_database_session_scope()
    next(dependency)

    with pytest.raises(RuntimeError, match="service failed"):
        dependency.throw(RuntimeError("service failed"))

    assert (scope.commits, scope.rollbacks, scope.closes) == (0, 1, 1)
