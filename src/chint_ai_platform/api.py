"""HTTP API for Agent runs."""

from functools import lru_cache
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, StringConstraints

from chint_ai_platform.agent_runs import AgentRunService, EchoAgentExecutor

NonBlankMessage = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class CreateAgentRunRequest(BaseModel):
    message: NonBlankMessage


class AgentRunResponse(BaseModel):
    run_id: str
    status: Literal["completed"]
    output: str


@lru_cache
def get_agent_run_service() -> AgentRunService:
    """Provide the process-wide default Agent run service."""
    return AgentRunService(EchoAgentExecutor())


router = APIRouter(prefix="/api/v1", tags=["agent-runs"])


@router.post(
    "/agent-runs",
    response_model=AgentRunResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_agent_run(
    request: CreateAgentRunRequest,
    service: Annotated[AgentRunService, Depends(get_agent_run_service)],
) -> AgentRunResponse:
    result = service.run(request.message)
    return AgentRunResponse(
        run_id=result.run_id,
        status=result.status,
        output=result.output,
    )
