from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from chint_ai_platform.agent_runs import (
    AgentRunService,
    AgentRunStateError,
    PersistedAgentRun,
    RecordedAgentRunService,
)
from chint_ai_platform.deepseek import DeepSeekTimeoutError
from chint_ai_platform.settings import DeepSeekNotConfiguredError


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


def test_persisted_run_starts_without_terminal_data() -> None:
    created_at = datetime(2026, 8, 20, 9, 30, tzinfo=UTC)

    run = PersistedAgentRun.start(
        run_id="d6109938-c9ba-4bc0-a20a-27e1b1fceb67",
        agent_id=None,
        input="分析本月异常",
        created_at=created_at,
    )

    assert run.status == "running"
    assert run.output is None
    assert run.error_code is None
    assert run.completed_at is None


def test_running_run_can_complete() -> None:
    created_at = datetime(2026, 8, 20, 9, 30, tzinfo=UTC)
    completed_at = created_at + timedelta(seconds=2)
    run = PersistedAgentRun.start("run-id", "agent-id", "输入", created_at)

    completed = run.complete("模型输出", completed_at)

    assert completed.status == "completed"
    assert completed.output == "模型输出"
    assert completed.error_code is None
    assert completed.completed_at == completed_at


def test_running_run_can_fail_with_stable_error_code() -> None:
    created_at = datetime(2026, 8, 20, 9, 30, tzinfo=UTC)
    failed_at = created_at + timedelta(seconds=1)
    run = PersistedAgentRun.start("run-id", None, "输入", created_at)

    failed = run.fail("deepseek_timeout", failed_at)

    assert failed.status == "failed"
    assert failed.output is None
    assert failed.error_code == "deepseek_timeout"
    assert failed.completed_at == failed_at


def test_terminal_run_rejects_another_transition() -> None:
    created_at = datetime(2026, 8, 20, 9, 30, tzinfo=UTC)
    completed = PersistedAgentRun.start("run-id", None, "输入", created_at).complete(
        "输出", created_at
    )

    with pytest.raises(AgentRunStateError):
        completed.fail("deepseek_timeout", created_at)


class RecordingRecorder:
    def __init__(self) -> None:
        self.events: list[tuple[str, object]] = []

    def start(self, agent_id: str | None, input: str) -> PersistedAgentRun:
        self.events.append(("start", (agent_id, input)))
        return PersistedAgentRun.start("persisted-run-id", agent_id, input, datetime.now(UTC))

    def complete(self, run_id: str, output: str) -> PersistedAgentRun:
        self.events.append(("complete", (run_id, output)))
        return PersistedAgentRun.start(run_id, None, "输入", datetime.now(UTC)).complete(
            output, datetime.now(UTC)
        )

    def fail(self, run_id: str, error_code: str) -> PersistedAgentRun:
        self.events.append(("fail", (run_id, error_code)))
        return PersistedAgentRun.start(run_id, None, "输入", datetime.now(UTC)).fail(
            error_code, datetime.now(UTC)
        )


class EventExecutor:
    def __init__(self, events: list[tuple[str, object]], error: Exception | None = None) -> None:
        self.events = events
        self.error = error

    def execute(self, system_prompt: str, message: str) -> str:
        self.events.append(("execute", (system_prompt, message)))
        if self.error:
            raise self.error
        return "输出"


def test_recorded_service_starts_before_execution_and_completes() -> None:
    recorder = RecordingRecorder()
    service = RecordedAgentRunService(EventExecutor(recorder.events), recorder)

    result = service.run("agent-id", "系统提示词", "输入")

    assert result.run_id == "persisted-run-id"
    assert recorder.events == [
        ("start", ("agent-id", "输入")),
        ("execute", ("系统提示词", "输入")),
        ("complete", ("persisted-run-id", "输出")),
    ]


def test_recorded_service_marks_deepseek_failure_and_binds_run_id() -> None:
    recorder = RecordingRecorder()
    error = DeepSeekTimeoutError("sensitive")
    service = RecordedAgentRunService(EventExecutor(recorder.events, error), recorder)

    with pytest.raises(DeepSeekTimeoutError) as raised:
        service.run(None, "系统提示词", "输入")

    assert raised.value.run_id == "persisted-run-id"
    assert recorder.events[-1] == ("fail", ("persisted-run-id", "deepseek_timeout"))


def test_recorded_service_marks_missing_configuration_as_failed() -> None:
    recorder = RecordingRecorder()
    error = DeepSeekNotConfiguredError("sensitive")
    service = RecordedAgentRunService(EventExecutor(recorder.events, error), recorder)

    with pytest.raises(DeepSeekNotConfiguredError) as raised:
        service.run(None, "系统提示词", "输入")

    assert raised.value.run_id == "persisted-run-id"
    assert recorder.events[-1] == (
        "fail",
        ("persisted-run-id", "deepseek_not_configured"),
    )
