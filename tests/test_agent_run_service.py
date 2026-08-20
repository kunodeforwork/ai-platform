from uuid import UUID

from chint_ai_platform.agent_runs import AgentRunService


class RecordingExecutor:
    def __init__(self, output: str) -> None:
        self.output = output
        self.received_requests: list[tuple[str, str]] = []

    def execute(self, system_prompt: str, message: str) -> str:
        self.received_requests.append((system_prompt, message))
        return self.output


def test_run_delegates_message_and_returns_completed_result() -> None:
    executor = RecordingExecutor(output="已处理")
    service = AgentRunService(executor)

    result = service.run("你是销售分析助手", "分析本月销售异常")

    assert executor.received_requests == [("你是销售分析助手", "分析本月销售异常")]
    assert result.status == "completed"
    assert result.output == "已处理"
    assert str(UUID(result.run_id)) == result.run_id
