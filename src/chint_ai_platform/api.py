"""HTTP API for Agent runs."""

from functools import lru_cache
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, FastAPI, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, StringConstraints

from chint_ai_platform.agent_runs import AgentRunService
from chint_ai_platform.deepseek import (
    DeepSeekAuthenticationError,
    DeepSeekRateLimitedError,
    DeepSeekTimeoutError,
    DeepSeekUpstreamError,
    EnvironmentDeepSeekAgentExecutor,
)
from chint_ai_platform.settings import DeepSeekNotConfiguredError

NonBlankMessage = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class CreateAgentRunRequest(BaseModel):
    message: NonBlankMessage


class AgentRunResponse(BaseModel):
    run_id: str
    status: Literal["completed"]
    output: str


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    error: ErrorDetail


ERROR_RESPONSES: dict[type[Exception], tuple[int, str, str]] = {
    DeepSeekNotConfiguredError: (
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "deepseek_not_configured",
        "DeepSeek API key is not configured",
    ),
    DeepSeekTimeoutError: (
        status.HTTP_504_GATEWAY_TIMEOUT,
        "deepseek_timeout",
        "DeepSeek request timed out",
    ),
    DeepSeekRateLimitedError: (
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "deepseek_rate_limited",
        "DeepSeek rate limit exceeded",
    ),
    DeepSeekAuthenticationError: (
        status.HTTP_502_BAD_GATEWAY,
        "deepseek_authentication_failed",
        "DeepSeek authentication failed",
    ),
    DeepSeekUpstreamError: (
        status.HTTP_502_BAD_GATEWAY,
        "deepseek_upstream_error",
        "DeepSeek upstream request failed",
    ),
}


def register_deepseek_exception_handlers(application: FastAPI) -> None:
    """Register safe HTTP mappings for failures at any dependency depth."""

    async def handle_deepseek_error(request: Request, error: Exception) -> JSONResponse:
        response_status, code, message = next(
            response
            for error_type, response in ERROR_RESPONSES.items()
            if isinstance(error, error_type)
        )
        return JSONResponse(
            status_code=response_status,
            content=ErrorResponse(error=ErrorDetail(code=code, message=message)).model_dump(),
        )

    for error_type in ERROR_RESPONSES:
        application.add_exception_handler(error_type, handle_deepseek_error)


@lru_cache
def get_agent_run_service() -> AgentRunService:
    """Provide the process-wide default Agent run service."""
    return AgentRunService(EnvironmentDeepSeekAgentExecutor())


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
