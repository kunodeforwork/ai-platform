"""Platform API key authentication boundary."""

import os
import secrets

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
