import pytest
from fastapi.testclient import TestClient

import chint_ai_platform.deepseek as deepseek_module
from chint_ai_platform.agent_runs import AgentRun
from chint_ai_platform.api import get_agent_run_service
from chint_ai_platform.deepseek import (
    DeepSeekAuthenticationError,
    DeepSeekRateLimitedError,
    DeepSeekTimeoutError,
    DeepSeekUpstreamError,
)
from chint_ai_platform.main import create_app
from chint_ai_platform.settings import DeepSeekNotConfiguredError


class RecordingAgentRunService:
    def __init__(self) -> None:
        self.received_messages: list[str] = []

    def run(self, message: str) -> AgentRun:
        self.received_messages.append(message)
        return AgentRun(
            run_id="d6109938-c9ba-4bc0-a20a-27e1b1fceb67",
            status="completed",
            output="发现华东区域销售异常",
        )


class RaisingAgentRunService:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def run(self, message: str) -> AgentRun:
        raise self.error


class SpecializedTimeoutError(DeepSeekTimeoutError):
    pass


def test_create_agent_run_delegates_and_maps_completed_result() -> None:
    service = RecordingAgentRunService()
    application = create_app()
    application.dependency_overrides[get_agent_run_service] = lambda: service

    response = TestClient(application).post(
        "/api/v1/agent-runs",
        json={"message": "分析本月销售异常"},
    )

    assert response.status_code == 201
    assert service.received_messages == ["分析本月销售异常"]
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
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    get_agent_run_service.cache_clear()

    try:
        response = TestClient(create_app(), raise_server_exceptions=False).post(
            "/api/v1/agent-runs",
            json={"message": "分析本月销售异常"},
        )
    finally:
        get_agent_run_service.cache_clear()

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "deepseek_not_configured",
            "message": "DeepSeek API key is not configured",
        }
    }


def test_default_service_maps_client_construction_failure_to_safe_upstream_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_to_create_client(**configuration: str) -> None:
        raise ValueError("sensitive client configuration detail")

    monkeypatch.setenv("DEEPSEEK_API_KEY", "secret")
    monkeypatch.setattr(deepseek_module, "OpenAI", fail_to_create_client)
    get_agent_run_service.cache_clear()

    try:
        response = TestClient(create_app(), raise_server_exceptions=False).post(
            "/api/v1/agent-runs",
            json={"message": "分析本月销售异常"},
        )
    finally:
        get_agent_run_service.cache_clear()

    assert response.status_code == 502
    assert response.json() == {
        "error": {
            "code": "deepseek_upstream_error",
            "message": "DeepSeek upstream request failed",
        }
    }


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
