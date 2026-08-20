from uuid import UUID

from chint_ai_platform.agent_runs import AgentRunService, EchoAgentExecutor


class RecordingExecutor:
    def __init__(self, output: str) -> None:
        self.output = output
        self.received_messages: list[str] = []

    def execute(self, message: str) -> str:
        self.received_messages.append(message)
        return self.output


def test_run_delegates_message_and_returns_completed_result() -> None:
    executor = RecordingExecutor(output="已处理")
    service = AgentRunService(executor)

    result = service.run("分析本月销售异常")

    assert executor.received_messages == ["分析本月销售异常"]
    assert result.status == "completed"
    assert result.output == "已处理"
    assert str(UUID(result.run_id)) == result.run_id


def test_echo_executor_returns_the_received_message() -> None:
    executor = EchoAgentExecutor()

    assert executor.execute("检查变压器告警") == "检查变压器告警"
