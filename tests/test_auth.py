import pytest
from fastapi import Depends, FastAPI
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

import chint_ai_platform.auth as auth_module
from chint_ai_platform.auth import (
    AuthenticationNotConfiguredError,
    InvalidApiKeyError,
    get_platform_api_key,
    register_auth_exception_handlers,
    require_api_key,
    validate_api_key,
)


def make_protected_app() -> FastAPI:
    application = FastAPI()
    register_auth_exception_handlers(application)

    @application.get("/protected", dependencies=[Depends(require_api_key)])
    def protected() -> dict[str, bool]:
        return {"ok": True}

    return application


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
        HTTPAuthorizationCredentials(scheme="Bearer", credentials=""),
        HTTPAuthorizationCredentials(scheme="Bearer", credentials="   "),
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


def test_authentication_not_configured_error_does_not_expose_credentials(monkeypatch):
    server_key = "server-sensitive-key-7319"
    client_key = "client-sensitive-key-8426"
    monkeypatch.delenv("PLATFORM_API_KEY", raising=False)

    with pytest.raises(AuthenticationNotConfiguredError) as error:
        validate_api_key(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=client_key)
        )

    assert server_key not in str(error.value)
    assert client_key not in str(error.value)


def test_invalid_api_key_error_does_not_expose_credentials(monkeypatch):
    server_key = "server-sensitive-key-7319"
    client_key = "client-sensitive-key-8426"
    monkeypatch.setenv("PLATFORM_API_KEY", server_key)

    with pytest.raises(InvalidApiKeyError) as error:
        validate_api_key(
            HTTPAuthorizationCredentials(scheme="Bearer", credentials=client_key)
        )

    assert server_key not in str(error.value)
    assert client_key not in str(error.value)


@pytest.mark.parametrize("authorization", [None, "", "Basic secret", "Bearer", "Bearer wrong-key"])
def test_all_invalid_authorization_headers_are_indistinguishable(
    monkeypatch, authorization
):
    monkeypatch.setenv("PLATFORM_API_KEY", "test-platform-key")
    headers = {} if authorization is None else {"Authorization": authorization}

    response = TestClient(make_protected_app()).get("/protected", headers=headers)

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json() == {
        "error": {"code": "invalid_api_key", "message": "Invalid API key"}
    }


@pytest.mark.parametrize("authorization", [None, "Bearer wrong-key"])
def test_missing_server_key_takes_priority_over_client_credentials(
    monkeypatch, authorization
):
    monkeypatch.delenv("PLATFORM_API_KEY", raising=False)
    headers = {} if authorization is None else {"Authorization": authorization}

    response = TestClient(make_protected_app()).get("/protected", headers=headers)

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "auth_not_configured",
            "message": "API authentication is not configured",
        }
    }
