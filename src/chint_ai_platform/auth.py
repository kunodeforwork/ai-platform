"""Platform API key authentication boundary."""

import os
import secrets
from typing import Annotated

from fastapi import FastAPI, Request, Security, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer


class AuthenticationNotConfiguredError(RuntimeError):
    """Raised when the server has no platform API key."""


class InvalidApiKeyError(PermissionError):
    """Raised when a client does not present the configured key."""


bearer_scheme = HTTPBearer(auto_error=False)


def get_platform_api_key() -> str:
    api_key = os.environ.get("PLATFORM_API_KEY", "").strip()
    if not api_key:
        raise AuthenticationNotConfiguredError("API authentication is not configured")
    return api_key


def validate_api_key(credentials: HTTPAuthorizationCredentials | None) -> None:
    configured_key = get_platform_api_key()
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise InvalidApiKeyError("Invalid API key")
    if not credentials.credentials or not secrets.compare_digest(
        credentials.credentials, configured_key
    ):
        raise InvalidApiKeyError("Invalid API key")


def require_api_key(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(bearer_scheme),
    ],
) -> None:
    validate_api_key(credentials)


def register_auth_exception_handlers(application: FastAPI) -> None:
    async def handle_not_configured(
        _request: Request,
        _error: AuthenticationNotConfiguredError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": {
                    "code": "auth_not_configured",
                    "message": "API authentication is not configured",
                }
            },
        )

    async def handle_invalid_key(
        _request: Request,
        _error: InvalidApiKeyError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            headers={"WWW-Authenticate": "Bearer"},
            content={
                "error": {
                    "code": "invalid_api_key",
                    "message": "Invalid API key",
                }
            },
        )

    application.add_exception_handler(
        AuthenticationNotConfiguredError,
        handle_not_configured,
    )
    application.add_exception_handler(InvalidApiKeyError, handle_invalid_key)
