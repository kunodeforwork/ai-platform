"""Application boundary for running an Agent."""

from dataclasses import dataclass, replace
from datetime import datetime
from typing import Literal, Protocol
from uuid import uuid4


class AgentExecutor(Protocol):
    """Execute one Agent message and return its textual output."""

    def execute(self, system_prompt: str, message: str) -> str: ...


class AgentRunRecorder(Protocol):
    def start(self, agent_id: str | None, input: str) -> "PersistedAgentRun": ...

    def complete(self, run_id: str, output: str) -> "PersistedAgentRun": ...

    def fail(self, run_id: str, error_code: str) -> "PersistedAgentRun": ...


@dataclass(frozen=True)
class AgentRun:
    """Completed Agent run returned by the application service."""

    run_id: str
    status: Literal["completed"]
    output: str


class AgentRunStateError(RuntimeError):
    """Raised when a terminal run is transitioned again."""


class AgentRunNotFoundError(LookupError):
    """Raised when a persisted run ID is unknown."""


@dataclass(frozen=True)
class PersistedAgentRun:
    id: str
    agent_id: str | None
    input: str
    output: str | None
    status: Literal["running", "completed", "failed"]
    error_code: str | None
    created_at: datetime
    completed_at: datetime | None

    @classmethod
    def start(
        cls,
        run_id: str,
        agent_id: str | None,
        input: str,
        created_at: datetime,
    ) -> "PersistedAgentRun":
        return cls(run_id, agent_id, input, None, "running", None, created_at, None)

    def complete(self, output: str, completed_at: datetime) -> "PersistedAgentRun":
        self._require_running()
        return replace(
            self,
            output=output,
            status="completed",
            error_code=None,
            completed_at=completed_at,
        )

    def fail(self, error_code: str, completed_at: datetime) -> "PersistedAgentRun":
        self._require_running()
        return replace(
            self,
            output=None,
            status="failed",
            error_code=error_code,
            completed_at=completed_at,
        )

    def _require_running(self) -> None:
        if self.status != "running":
            raise AgentRunStateError(f"Cannot transition run in {self.status} state")


class AgentRunService:
    """Coordinate creation and execution of an Agent run."""

    def __init__(self, executor: AgentExecutor) -> None:
        self._executor = executor

    def run(self, system_prompt: str, message: str) -> AgentRun:
        output = self._executor.execute(system_prompt, message)
        return AgentRun(run_id=str(uuid4()), status="completed", output=output)


class RecordedAgentRunService:
    """Execute an Agent while durably recording its state transitions."""

    def __init__(self, executor: AgentExecutor, recorder: AgentRunRecorder) -> None:
        self._executor = executor
        self._recorder = recorder

    def run(self, agent_id: str | None, system_prompt: str, message: str) -> AgentRun:
        from chint_ai_platform.deepseek import DeepSeekExecutorError
        from chint_ai_platform.settings import DeepSeekNotConfiguredError

        persisted = self._recorder.start(agent_id, message)
        try:
            output = self._executor.execute(system_prompt, message)
        except (DeepSeekExecutorError, DeepSeekNotConfiguredError) as error:
            self._recorder.fail(persisted.id, error.error_code)
            error.bind_run_id(persisted.id)
            raise
        self._recorder.complete(persisted.id, output)
        return AgentRun(run_id=persisted.id, status="completed", output=output)
