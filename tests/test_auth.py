import pytest
from fastapi.security import HTTPAuthorizationCredentials

import chint_ai_platform.auth as auth_module
from chint_ai_platform.auth import (
    AuthenticationNotConfiguredError,
    InvalidApiKeyError,
    get_platform_api_key,
    validate_api_key,
)


@pytest.mark.parametrize("value", [None, "", "   "])
def test_platform_api_key_must_be_configured(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("PLATFORM_API_KEY", raising=False)
    else:
        monkeypatch.setenv("PLATFORM_API_KEY", value)
    with pytest.raises(AuthenticationNotConfiguredError):
        get_platform_api_key()


@pytest.mark.parametrize(
    "credentials",
    [
        None,
        HTTPAuthorizationCredentials(scheme="Basic", credentials="secret"),
        HTTPAuthorizationCredentials(scheme="Bearer", credentials="wrong"),
    ],
)
def test_validate_api_key_rejects_all_invalid_credentials(monkeypatch, credentials):
    monkeypatch.setenv("PLATFORM_API_KEY", "test-platform-key")
    with pytest.raises(InvalidApiKeyError):
        validate_api_key(credentials)


def test_validate_api_key_accepts_matching_bearer_credentials(monkeypatch):
    monkeypatch.setenv("PLATFORM_API_KEY", "test-platform-key")

    validate_api_key(
        HTTPAuthorizationCredentials(scheme="Bearer", credentials="test-platform-key")
    )


def test_validate_api_key_uses_compare_digest(monkeypatch):
    compared = []
    monkeypatch.setenv("PLATFORM_API_KEY", "test-platform-key")
    monkeypatch.setattr(
        auth_module.secrets,
        "compare_digest",
        lambda presented, configured: compared.append((presented, configured)) or True,
    )

    validate_api_key(HTTPAuthorizationCredentials(scheme="Bearer", credentials="client-key"))

    assert compared == [("client-key", "test-platform-key")]
