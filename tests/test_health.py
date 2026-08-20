from fastapi.testclient import TestClient

from chint_ai_platform.main import create_app


def test_health_reports_service_is_up() -> None:
    response = TestClient(create_app()).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
