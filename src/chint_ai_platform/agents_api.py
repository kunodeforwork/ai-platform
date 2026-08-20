"""HTTP API for Agent configurations."""

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, StringConstraints

from chint_ai_platform.agents import (
    Agent,
    AgentNotFoundError,
    AgentService,
    ConfiguredAgentRunService,
    InMemoryAgentRepository,
)
from chint_ai_platform.api import (
    AgentRunResponse,
    CreateAgentRunRequest,
    get_agent_run_service,
)

AgentName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
AgentDescription = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
SystemPrompt = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=4000),
]


class CreateAgentRequest(BaseModel):
    name: AgentName
    description: AgentDescription = ""
    system_prompt: SystemPrompt


class AgentResponse(BaseModel):
    id: str
    name: str
    description: str
    system_prompt: str
    created_at: datetime

    @classmethod
    def from_agent(cls, agent: Agent) -> "AgentResponse":
        return cls(
            id=agent.id,
            name=agent.name,
            description=agent.description,
            system_prompt=agent.system_prompt,
            created_at=agent.created_at,
        )


_AGENT_REPOSITORY = InMemoryAgentRepository()
_AGENT_SERVICE = AgentService(_AGENT_REPOSITORY)
_CONFIGURED_AGENT_RUN_SERVICE = ConfiguredAgentRunService(
    _AGENT_SERVICE,
    get_agent_run_service(),
)


def get_agent_repository() -> InMemoryAgentRepository:
    return _AGENT_REPOSITORY


def get_agent_service() -> AgentService:
    return _AGENT_SERVICE


def get_configured_agent_run_service() -> ConfiguredAgentRunService:
    return _CONFIGURED_AGENT_RUN_SERVICE


def register_agent_exception_handlers(application: FastAPI) -> None:
    async def handle_not_found(request: Request, error: AgentNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": {"code": "agent_not_found", "message": "Agent not found"}},
        )

    application.add_exception_handler(AgentNotFoundError, handle_not_found)


router = APIRouter(prefix="/api/v1/agents", tags=["agents"])


@router.post("", response_model=AgentResponse, status_code=status.HTTP_201_CREATED)
def create_agent(
    request: CreateAgentRequest,
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> AgentResponse:
    agent = service.create(request.name, request.description, request.system_prompt)
    return AgentResponse.from_agent(agent)


@router.get("/{agent_id}", response_model=AgentResponse)
def get_agent(
    agent_id: UUID,
    service: Annotated[AgentService, Depends(get_agent_service)],
) -> AgentResponse:
    return AgentResponse.from_agent(service.get(str(agent_id)))


@router.post(
    "/{agent_id}/runs",
    response_model=AgentRunResponse,
    status_code=status.HTTP_201_CREATED,
)
def run_agent(
    agent_id: UUID,
    request: CreateAgentRunRequest,
    service: Annotated[
        ConfiguredAgentRunService,
        Depends(get_configured_agent_run_service),
    ],
) -> AgentRunResponse:
    result = service.run(str(agent_id), request.message)
    return AgentRunResponse(
        run_id=result.run_id,
        status=result.status,
        output=result.output,
    )
