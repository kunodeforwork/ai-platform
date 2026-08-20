"""Agent configuration domain and storage boundaries."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Protocol
from uuid import UUID, uuid4

from chint_ai_platform.agent_runs import AgentRun


@dataclass(frozen=True)
class Agent:
    id: str
    name: str
    description: str
    system_prompt: str
    created_at: datetime


class AgentNotFoundError(LookupError):
    """Raised when an Agent ID is not present in the repository."""


class AgentRepository(Protocol):
    def add(self, agent: Agent) -> None: ...

    def get(self, agent_id: str) -> Agent | None: ...


class InMemoryAgentRepository:
    """Process-local, thread-safe Agent repository."""

    def __init__(self) -> None:
        self._agents: dict[str, Agent] = {}
        self._lock = Lock()

    def add(self, agent: Agent) -> None:
        with self._lock:
            self._agents[agent.id] = agent

    def get(self, agent_id: str) -> Agent | None:
        with self._lock:
            return self._agents.get(agent_id)


class AgentService:
    """Create and retrieve immutable Agent configurations."""

    def __init__(
        self,
        repository: AgentRepository,
        *,
        id_factory: Callable[[], UUID] = uuid4,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._repository = repository
        self._id_factory = id_factory
        self._clock = clock

    def create(self, name: str, description: str, system_prompt: str) -> Agent:
        agent = Agent(
            id=str(self._id_factory()),
            name=name.strip(),
            description=description.strip(),
            system_prompt=system_prompt.strip(),
            created_at=self._clock(),
        )
        self._repository.add(agent)
        return agent

    def get(self, agent_id: str) -> Agent:
        agent = self._repository.get(agent_id)
        if agent is None:
            raise AgentNotFoundError(agent_id)
        return agent


class AgentRunGateway(Protocol):
    def run(self, system_prompt: str, message: str) -> AgentRun: ...


class ConfiguredAgentRunService:
    """Run a message using the system prompt of a stored Agent."""

    def __init__(self, agents: AgentService, runs: AgentRunGateway) -> None:
        self._agents = agents
        self._runs = runs

    def run(self, agent_id: str, message: str) -> AgentRun:
        agent = self._agents.get(agent_id)
        return self._runs.run(agent.system_prompt, message)
