"""Application boundary for running an Agent."""

from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import uuid4


class AgentExecutor(Protocol):
    """Execute one Agent message and return its textual output."""

    def execute(self, system_prompt: str, message: str) -> str: ...


@dataclass(frozen=True)
class AgentRun:
    """Completed Agent run returned by the application service."""

    run_id: str
    status: Literal["completed"]
    output: str


class AgentRunService:
    """Coordinate creation and execution of an Agent run."""

    def __init__(self, executor: AgentExecutor) -> None:
        self._executor = executor

    def run(self, system_prompt: str, message: str) -> AgentRun:
        output = self._executor.execute(system_prompt, message)
        return AgentRun(run_id=str(uuid4()), status="completed", output=output)
