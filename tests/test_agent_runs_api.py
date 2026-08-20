from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

import chint_ai_platform.deepseek as deepseek_module
import chint_ai_platform.persistence as persistence_module
from chint_ai_platform.agent_runs import AgentRun, AgentRunNotFoundError, PersistedAgentRun
from chint_ai_platform.api import get_agent_run_recorder, get_agent_run_service
from chint_ai_platform.deepseek import (
    DEFAULT_SYSTEM_PROMPT,
    DeepSeekAuthenticationError,
    DeepSeekRateLimitedError,
    DeepSeekTimeoutError,
    DeepSeekUpstreamError,
)
from chint_ai_platform.main import create_app
from chint_ai_platform.persistence import Base
from chint_ai_platform.settings import DeepSeekNotConfiguredError


class RecordingAgentRunService:
    def __init__(self) -> None:
        self.received_requests: list[tuple[str | None, str, str]] = []

    def run(self, agent_id: str | None, system_prompt: str, message: str) -> AgentRun:
        self.received_requests.append((agent_id, system_prompt, message))
        return AgentRun(
            run_id="d6109938-c9ba-4bc0-a20a-27e1b1fceb67",
            status="completed",
            output="发现华东区域销售异常",
        )


class RaisingAgentRunService:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def run(self, agent_id: str | None, system_prompt: str, message: str) -> AgentRun:
        raise self.error


class SpecializedTimeoutError(DeepSeekTimeoutError):
    pass


class RecordingRunQuery:
    def get(self, run_id: str) -> PersistedAgentRun:
        if run_id != "d6109938-c9ba-4bc0-a20a-27e1b1fceb67":
            raise AgentRunNotFoundError(run_id)
        return PersistedAgentRun.start(
            run_id, None, "输入", datetime(2026, 8, 20, 9, 30, tzinfo=UTC)
        ).complete("输出", datetime(2026, 8, 20, 9, 31, tzinfo=UTC))


def test_create_agent_run_delegates_and_maps_completed_result() -> None:
    service = RecordingAgentRunService()
    application = create_app()
    application.dependency_overrides[get_agent_run_service] = lambda: service

    response = TestClient(application).post(
        "/api/v1/agent-runs",
        json={"message": "分析本月销售异常"},
    )

    assert response.status_code == 201
    assert service.received_requests == [(None, DEFAULT_SYSTEM_PROMPT, "分析本月销售异常")]
    assert response.json() == {
        "run_id": "d6109938-c9ba-4bc0-a20a-27e1b1fceb67",
        "status": "completed",
        "output": "发现华东区域销售异常",
    }


def test_create_agent_run_rejects_whitespace_only_message() -> None:
    response = TestClient(create_app()).post(
        "/api/v1/agent-runs",
        json={"message": "   "},
    )

    assert response.status_code == 422


def test_default_agent_run_service_reports_missing_deepseek_key(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    database_url = f"sqlite:///{tmp_path / 'runs.db'}"
    Base.metadata.create_all(create_engine(database_url))
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    persistence_module._SESSION_FACTORY = None
    get_agent_run_recorder.cache_clear()
    get_agent_run_service.cache_clear()

    try:
        client = TestClient(create_app(), raise_server_exceptions=False)
        response = client.post(
            "/api/v1/agent-runs",
            json={"message": "分析本月销售异常"},
        )
        run_response = client.get(f"/api/v1/agent-runs/{response.json()['run_id']}")
    finally:
        get_agent_run_service.cache_clear()
        get_agent_run_recorder.cache_clear()
        persistence_module._SESSION_FACTORY = None

    assert response.status_code == 503
    body = response.json()
    assert str(UUID(body["run_id"])) == body["run_id"]
    assert body["error"] == {
        "code": "deepseek_not_configured",
        "message": "DeepSeek API key is not configured",
    }
    assert run_response.status_code == 200
    assert run_response.json()["status"] == "failed"
    assert run_response.json()["error_code"] == "deepseek_not_configured"


def test_default_service_maps_client_construction_failure_to_safe_upstream_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    def fail_to_create_client(**configuration: str) -> None:
        raise ValueError("sensitive client configuration detail")

    database_url = f"sqlite:///{tmp_path / 'runs.db'}"
    Base.metadata.create_all(create_engine(database_url))
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")
    monkeypatch.setattr(deepseek_module, "OpenAI", fail_to_create_client)
    persistence_module._SESSION_FACTORY = None
    get_agent_run_recorder.cache_clear()
    get_agent_run_service.cache_clear()

    try:
        client = TestClient(create_app(), raise_server_exceptions=False)
        response = client.post(
            "/api/v1/agent-runs",
            json={"message": "分析本月销售异常"},
        )
        run_response = client.get(f"/api/v1/agent-runs/{response.json()['run_id']}")
    finally:
        get_agent_run_service.cache_clear()
        get_agent_run_recorder.cache_clear()
        persistence_module._SESSION_FACTORY = None

    assert response.status_code == 502
    body = response.json()
    assert str(UUID(body["run_id"])) == body["run_id"]
    assert body["error"] == {
        "code": "deepseek_upstream_error",
        "message": "DeepSeek upstream request failed",
    }
    assert run_response.status_code == 200
    assert run_response.json()["id"] == body["run_id"]
    assert run_response.json()["status"] == "failed"
    assert run_response.json()["error_code"] == "deepseek_upstream_error"


def test_create_agent_run_maps_boundary_exception_subclass() -> None:
    application = create_app()
    application.dependency_overrides[get_agent_run_service] = lambda: RaisingAgentRunService(
        SpecializedTimeoutError("sensitive timeout detail")
    )

    response = TestClient(application, raise_server_exceptions=False).post(
        "/api/v1/agent-runs",
        json={"message": "分析本月销售异常"},
    )

    assert response.status_code == 504
    assert response.json() == {
        "error": {
            "code": "deepseek_timeout",
            "message": "DeepSeek request timed out",
        }
    }


@pytest.mark.parametrize(
    ("error", "expected_status", "expected_code", "expected_message"),
    [
        (
            DeepSeekNotConfiguredError("sensitive config detail"),
            503,
            "deepseek_not_configured",
            "DeepSeek API key is not configured",
        ),
        (
            DeepSeekTimeoutError("sensitive timeout detail"),
            504,
            "deepseek_timeout",
            "DeepSeek request timed out",
        ),
        (
            DeepSeekRateLimitedError("sensitive rate detail"),
            503,
            "deepseek_rate_limited",
            "DeepSeek rate limit exceeded",
        ),
        (
            DeepSeekAuthenticationError("sensitive auth detail"),
            502,
            "deepseek_authentication_failed",
            "DeepSeek authentication failed",
        ),
        (
            DeepSeekUpstreamError("sensitive upstream detail"),
            502,
            "deepseek_upstream_error",
            "DeepSeek upstream request failed",
        ),
    ],
)
def test_create_agent_run_maps_deepseek_errors_to_safe_response(
    error: Exception,
    expected_status: int,
    expected_code: str,
    expected_message: str,
) -> None:
    application = create_app()
    application.dependency_overrides[get_agent_run_service] = lambda: RaisingAgentRunService(
        error
    )

    response = TestClient(application, raise_server_exceptions=False).post(
        "/api/v1/agent-runs",
        json={"message": "分析本月销售异常"},
    )

    assert response.status_code == expected_status
    assert response.json() == {
        "error": {"code": expected_code, "message": expected_message}
    }


def test_get_agent_run_returns_persisted_record() -> None:
    application = create_app()
    application.dependency_overrides[get_agent_run_recorder] = RecordingRunQuery

    response = TestClient(application).get(
        "/api/v1/agent-runs/d6109938-c9ba-4bc0-a20a-27e1b1fceb67"
    )

    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert response.json()["output"] == "输出"


def test_get_unknown_agent_run_returns_safe_not_found() -> None:
    application = create_app()
    application.dependency_overrides[get_agent_run_recorder] = RecordingRunQuery

    response = TestClient(application).get(
        "/api/v1/agent-runs/8e52ea3a-f9ec-41b8-9464-e21e4c4ef9e9"
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "agent_run_not_found", "message": "Agent run not found"}
    }
