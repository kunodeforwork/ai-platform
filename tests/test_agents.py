from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from uuid import UUID

import pytest

from chint_ai_platform.agent_runs import AgentRun
from chint_ai_platform.agents import (
    Agent,
    AgentNotFoundError,
    AgentService,
    ConfiguredAgentRunService,
    InMemoryAgentRepository,
)

CREATED_AT = datetime(2026, 8, 20, 9, 30, tzinfo=UTC)


def test_agent_service_creates_normalized_agent() -> None:
    repository = InMemoryAgentRepository()
    service = AgentService(repository, clock=lambda: CREATED_AT)

    agent = service.create(
        name="  销售分析助手  ",
        description="  分析区域销售异常  ",
        system_prompt="  请给出可验证的分析。  ",
    )

    assert str(UUID(agent.id)) == agent.id
    assert agent.name == "销售分析助手"
    assert agent.description == "分析区域销售异常"
    assert agent.system_prompt == "请给出可验证的分析。"
    assert agent.created_at == CREATED_AT
    assert repository.get(agent.id) == agent


def test_agent_service_returns_existing_agent() -> None:
    repository = InMemoryAgentRepository()
    service = AgentService(repository, clock=lambda: CREATED_AT)
    created = service.create("助手", "", "系统提示词")

    assert service.get(created.id) == created


def test_agent_service_rejects_unknown_agent() -> None:
    service = AgentService(InMemoryAgentRepository(), clock=lambda: CREATED_AT)

    with pytest.raises(AgentNotFoundError):
        service.get("8e52ea3a-f9ec-41b8-9464-e21e4c4ef9e9")


def test_in_memory_repository_keeps_parallel_writes() -> None:
    repository = InMemoryAgentRepository()
    agents = [
        Agent(str(index), f"Agent {index}", "", "Prompt", CREATED_AT)
        for index in range(50)
    ]

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(repository.add, agents))

    assert [repository.get(agent.id) for agent in agents] == agents


class RecordingRunService:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str]] = []

    def run(self, system_prompt: str, message: str) -> AgentRun:
        self.requests.append((system_prompt, message))
        return AgentRun("run-id", "completed", "分析完成")


def test_configured_run_uses_selected_agent_system_prompt() -> None:
    agents = AgentService(InMemoryAgentRepository(), clock=lambda: CREATED_AT)
    agent = agents.create("销售助手", "", "只分析销售数据")
    runs = RecordingRunService()
    service = ConfiguredAgentRunService(agents, runs)

    result = service.run(agent.id, "分析本月异常")

    assert runs.requests == [("只分析销售数据", "分析本月异常")]
    assert result.output == "分析完成"
