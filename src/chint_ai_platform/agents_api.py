"""HTTP API for Agent configurations."""

from collections.abc import Iterator
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, StringConstraints

from chint_ai_platform.agent_runs import RecordedAgentRunService
from chint_ai_platform.agents import (
    Agent,
    AgentNotFoundError,
    AgentService,
    ConfiguredAgentRunService,
)
from chint_ai_platform.api import (
    AgentRunResponse,
    CreateAgentRunRequest,
    get_agent_run_service,
)
from chint_ai_platform.persistence import (
    DatabaseSessionScope,
    DatabaseUnavailableError,
    SqlAlchemyAgentRepository,
    get_session_factory,
)
from chint_ai_platform.settings import DatabaseNotConfiguredError

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


def get_database_session_scope() -> Iterator[DatabaseSessionScope]:
    scope = DatabaseSessionScope(get_session_factory)
    try:
        yield scope
        scope.commit()
    except Exception:
        scope.rollback()
        raise
    finally:
        scope.close()


def get_agent_service(
    scope: Annotated[
        DatabaseSessionScope,
        Depends(get_database_session_scope, scope="function"),
    ],
) -> AgentService:
    return AgentService(SqlAlchemyAgentRepository(scope))


def get_configured_agent_run_service(
    agents: Annotated[AgentService, Depends(get_agent_service)],
    runs: Annotated[RecordedAgentRunService, Depends(get_agent_run_service)],
) -> ConfiguredAgentRunService:
    return ConfiguredAgentRunService(agents, runs)


def register_agent_exception_handlers(application: FastAPI) -> None:
    async def handle_not_found(request: Request, error: AgentNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"error": {"code": "agent_not_found", "message": "Agent not found"}},
        )

    application.add_exception_handler(AgentNotFoundError, handle_not_found)

    async def handle_database_error(request: Request, error: Exception) -> JSONResponse:
        if isinstance(error, DatabaseNotConfiguredError):
            code, message = "database_not_configured", "Database is not configured"
        else:
            code, message = "database_unavailable", "Database is unavailable"
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"error": {"code": code, "message": message}},
        )

    application.add_exception_handler(DatabaseNotConfiguredError, handle_database_error)
    application.add_exception_handler(DatabaseUnavailableError, handle_database_error)


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
