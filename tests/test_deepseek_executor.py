from types import SimpleNamespace
from typing import Any

import httpx
import openai
import pytest

import chint_ai_platform.deepseek as deepseek_module
from chint_ai_platform.deepseek import (
    SYSTEM_PROMPT,
    DeepSeekAgentExecutor,
    DeepSeekAuthenticationError,
    DeepSeekRateLimitedError,
    DeepSeekTimeoutError,
    DeepSeekUpstreamError,
    EnvironmentDeepSeekAgentExecutor,
)
from chint_ai_platform.settings import DeepSeekSettings


class RecordingCompletions:
    def __init__(self, response: object) -> None:
        self.response = response
        self.requests: list[dict[str, Any]] = []

    def create(self, **request: Any) -> object:
        self.requests.append(request)
        return self.response


class RecordingClient:
    def __init__(self, response: object) -> None:
        self.completions = RecordingCompletions(response)
        self.chat = SimpleNamespace(completions=self.completions)


class FailingCompletions:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def create(self, **request: Any) -> object:
        raise self.error


class FailingClient:
    def __init__(self, error: Exception) -> None:
        self.chat = SimpleNamespace(completions=FailingCompletions(error))


def make_executor(client: object) -> DeepSeekAgentExecutor:
    return DeepSeekAgentExecutor(DeepSeekSettings(api_key="secret"), client=client)


def test_executor_sends_non_thinking_v4_flash_request() -> None:
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="发现华东区域销售异常"))]
    )
    client = RecordingClient(response)
    executor = DeepSeekAgentExecutor(
        DeepSeekSettings(api_key="secret"),
        client=client,
    )

    result = executor.execute("分析本月销售异常")

    assert result == "发现华东区域销售异常"
    assert client.completions.requests == [
        {
            "model": "deepseek-v4-flash",
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": "分析本月销售异常"},
            ],
            "stream": False,
            "extra_body": {"thinking": {"type": "disabled"}},
        }
    ]


@pytest.mark.parametrize(
    "response",
    [
        SimpleNamespace(choices=[]),
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=None))]),
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="   "))]),
    ],
)
def test_executor_rejects_missing_or_blank_content(response: object) -> None:
    with pytest.raises(DeepSeekUpstreamError):
        make_executor(RecordingClient(response)).execute("检查告警")


def upstream_errors() -> list[tuple[Exception, type[Exception]]]:
    request = httpx.Request("POST", "https://api.deepseek.com/chat/completions")
    return [
        (openai.APITimeoutError(request), DeepSeekTimeoutError),
        (
            openai.RateLimitError(
                "rate limited",
                response=httpx.Response(429, request=request),
                body=None,
            ),
            DeepSeekRateLimitedError,
        ),
        (
            openai.AuthenticationError(
                "invalid key",
                response=httpx.Response(401, request=request),
                body=None,
            ),
            DeepSeekAuthenticationError,
        ),
        (openai.APIConnectionError(request=request), DeepSeekUpstreamError),
        (
            openai.APIStatusError(
                "upstream failed",
                response=httpx.Response(500, request=request),
                body=None,
            ),
            DeepSeekUpstreamError,
        ),
    ]


@pytest.mark.parametrize(("sdk_error", "expected_error"), upstream_errors())
def test_executor_translates_sdk_errors(
    sdk_error: Exception,
    expected_error: type[Exception],
) -> None:
    with pytest.raises(expected_error):
        make_executor(FailingClient(sdk_error)).execute("检查告警")


def test_environment_executor_builds_client_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="已完成分析"))]
    )
    client = RecordingClient(response)
    client_configurations: list[dict[str, str]] = []

    def create_client(**configuration: str) -> RecordingClient:
        client_configurations.append(configuration)
        return client

    monkeypatch.setenv("DEEPSEEK_API_KEY", "environment-secret")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://gateway.example/v1")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-v4-flash")
    monkeypatch.setattr(deepseek_module, "OpenAI", create_client)

    result = EnvironmentDeepSeekAgentExecutor().execute("检查告警")

    assert result == "已完成分析"
    assert client_configurations == [
        {
            "api_key": "environment-secret",
            "base_url": "https://gateway.example/v1",
        }
    ]
    assert client.completions.requests[0]["model"] == "deepseek-v4-flash"
