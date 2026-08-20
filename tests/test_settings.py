import pytest

from chint_ai_platform.settings import (
    DatabaseNotConfiguredError,
    DatabaseSettings,
    DeepSeekNotConfiguredError,
    DeepSeekSettings,
)


def test_settings_use_deepseek_defaults() -> None:
    settings = DeepSeekSettings.from_environment({"DEEPSEEK_API_KEY": "secret"})

    assert settings.api_key == "secret"
    assert settings.base_url == "https://api.deepseek.com"
    assert settings.model == "deepseek-v4-flash"


def test_settings_allow_endpoint_and_model_overrides() -> None:
    settings = DeepSeekSettings.from_environment(
        {
            "DEEPSEEK_API_KEY": "secret",
            "DEEPSEEK_BASE_URL": "https://gateway.example/v1",
            "DEEPSEEK_MODEL": "deployment-name",
        }
    )

    assert settings.base_url == "https://gateway.example/v1"
    assert settings.model == "deployment-name"


@pytest.mark.parametrize("api_key", [None, "", "   "])
def test_settings_reject_missing_or_blank_api_key(api_key: str | None) -> None:
    environment = {} if api_key is None else {"DEEPSEEK_API_KEY": api_key}

    with pytest.raises(DeepSeekNotConfiguredError):
        DeepSeekSettings.from_environment(environment)


def test_database_settings_read_database_url() -> None:
    settings = DatabaseSettings.from_environment(
        {"DATABASE_URL": "postgresql+psycopg://user:password@db/app"}
    )

    assert settings.url == "postgresql+psycopg://user:password@db/app"


@pytest.mark.parametrize("database_url", [None, "", "   "])
def test_database_settings_reject_missing_or_blank_url(database_url: str | None) -> None:
    environment = {} if database_url is None else {"DATABASE_URL": database_url}

    with pytest.raises(DatabaseNotConfiguredError):
        DatabaseSettings.from_environment(environment)
