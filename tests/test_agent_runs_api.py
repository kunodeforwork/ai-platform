from fastapi.testclient import TestClient

from chint_ai_platform.agent_runs import AgentRun
from chint_ai_platform.api import get_agent_run_service
from chint_ai_platform.main import create_app


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
