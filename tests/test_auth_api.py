import pytest
from fastapi.testclient import TestClient

from chint_ai_platform.api import get_agent_run_service
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


def test_openapi_declares_bearer_security_only_for_business_routes():
    schema = create_app().openapi()
    schemes = schema["components"]["securitySchemes"]
    bearer_name = next(
        name
        for name, value in schemes.items()
        if value["type"] == "http" and value["scheme"] == "bearer"
    )
    assert schema["paths"]["/api/v1/agent-runs"]["post"]["security"] == [
        {bearer_name: []}
    ]
    assert schema["paths"]["/api/v1/agents"]["post"]["security"] == [
        {bearer_name: []}
    ]
    assert "security" not in schema["paths"]["/health"]["get"]


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
