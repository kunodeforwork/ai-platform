import pytest


@pytest.fixture
def configured_api_key(monkeypatch: pytest.MonkeyPatch) -> str:
    api_key = "test-platform-key"
    monkeypatch.setenv("PLATFORM_API_KEY", api_key)
    return api_key


@pytest.fixture
def auth_headers(configured_api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {configured_api_key}"}
