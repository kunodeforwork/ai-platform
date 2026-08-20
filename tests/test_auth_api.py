import pytest
from fastapi.testclient import TestClient

import chint_ai_platform.agents_api as agents_api_module
from chint_ai_platform.api import get_agent_run_service
from chint_ai_platform.main import create_app

RESOURCE_ID = "5b1c53ef-6cd7-4537-81b6-d37ef87c5f69"


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("post", "/api/v1/agent-runs", {"message": "分析异常"}),
        ("get", f"/api/v1/agent-runs/{RESOURCE_ID}", None),
        (
            "post",
            "/api/v1/agents",
            {
                "name": "销售分析助手",
                "description": "分析异常",
                "system_prompt": "只分析销售数据",
            },
        ),
        ("get", f"/api/v1/agents/{RESOURCE_ID}", None),
        ("post", f"/api/v1/agents/{RESOURCE_ID}/runs", {"message": "分析异常"}),
    ],
)
def test_business_routes_require_api_key(monkeypatch, method, path, payload):
    monkeypatch.setenv("PLATFORM_API_KEY", "test-platform-key")
    request = getattr(TestClient(create_app()), method)
    response = request(path) if payload is None else request(path, json=payload)
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
    operations = [
        ("/api/v1/agent-runs", "post"),
        ("/api/v1/agent-runs/{run_id}", "get"),
        ("/api/v1/agents", "post"),
        ("/api/v1/agents/{agent_id}", "get"),
        ("/api/v1/agents/{agent_id}/runs", "post"),
    ]
    for path, method in operations:
        assert schema["paths"][path][method]["security"] == [{bearer_name: []}]
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


def test_authentication_failure_does_not_create_database_session_scope(monkeypatch):
    called = False

    def forbidden_database_session_scope():
        nonlocal called
        called = True
        raise AssertionError("database session scope must not be resolved")

    monkeypatch.setenv("PLATFORM_API_KEY", "test-platform-key")
    application = create_app()
    application.dependency_overrides[agents_api_module.get_database_session_scope] = (
        forbidden_database_session_scope
    )
    response = TestClient(application).post(
        "/api/v1/agents",
        json={
            "name": "销售分析助手",
            "description": "分析异常",
            "system_prompt": "只分析销售数据",
        },
    )
    assert response.status_code == 401
    assert called is False
