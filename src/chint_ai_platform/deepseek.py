"""DeepSeek implementation of the Agent executor boundary."""

from threading import Lock
from typing import Any

import openai
from openai import OpenAI

from chint_ai_platform.settings import DeepSeekNotConfiguredError, DeepSeekSettings

DEFAULT_SYSTEM_PROMPT = (
    "你是正泰企业 AI 助手。请准确、简洁地回答；信息不足时明确说明，不要编造。"
)


class DeepSeekExecutorError(RuntimeError):
    """Base class for safe DeepSeek boundary failures."""

    error_code = "deepseek_upstream_error"

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.run_id: str | None = None

    def bind_run_id(self, run_id: str) -> None:
        self.run_id = run_id


class DeepSeekTimeoutError(DeepSeekExecutorError):
    """Raised when DeepSeek does not respond before the SDK timeout."""

    error_code = "deepseek_timeout"


class DeepSeekRateLimitedError(DeepSeekExecutorError):
    """Raised when DeepSeek rejects a request due to rate limiting."""

    error_code = "deepseek_rate_limited"


class DeepSeekAuthenticationError(DeepSeekExecutorError):
    """Raised when DeepSeek rejects the configured credential."""

    error_code = "deepseek_authentication_failed"


class DeepSeekUpstreamError(DeepSeekExecutorError):
    """Raised for invalid responses and remaining upstream failures."""


class DeepSeekAgentExecutor:
    """Execute a single non-thinking DeepSeek chat completion."""

    def __init__(self, settings: DeepSeekSettings, client: Any) -> None:
        self._settings = settings
        self._client = client

    def execute(self, system_prompt: str, message: str) -> str:
        try:
            response = self._client.chat.completions.create(
                model=self._settings.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": message},
                ],
                stream=False,
                extra_body={"thinking": {"type": "disabled"}},
            )
        except openai.APITimeoutError as error:
            raise DeepSeekTimeoutError("DeepSeek request timed out") from error
        except openai.RateLimitError as error:
            raise DeepSeekRateLimitedError("DeepSeek rate limit exceeded") from error
        except openai.AuthenticationError as error:
            raise DeepSeekAuthenticationError("DeepSeek authentication failed") from error
        except openai.OpenAIError as error:
            raise DeepSeekUpstreamError("DeepSeek upstream request failed") from error

        try:
            content = response.choices[0].message.content
        except (AttributeError, IndexError, TypeError) as error:
            raise DeepSeekUpstreamError("DeepSeek returned an invalid response") from error
        if not isinstance(content, str) or not content.strip():
            raise DeepSeekUpstreamError("DeepSeek returned an invalid response")
        return content


class EnvironmentDeepSeekAgentExecutor:
    """Lazily configure DeepSeek after FastAPI has validated the request body."""

    def __init__(self) -> None:
        self._executor_instance: DeepSeekAgentExecutor | None = None
        self._initialization_lock = Lock()

    def _get_executor(self) -> DeepSeekAgentExecutor:
        if self._executor_instance is not None:
            return self._executor_instance
        with self._initialization_lock:
            if self._executor_instance is None:
                try:
                    settings = DeepSeekSettings.from_environment()
                    client = OpenAI(api_key=settings.api_key, base_url=settings.base_url)
                except DeepSeekNotConfiguredError:
                    raise
                except Exception as error:
                    raise DeepSeekUpstreamError(
                        "DeepSeek client configuration failed"
                    ) from error
                self._executor_instance = DeepSeekAgentExecutor(settings, client=client)
            return self._executor_instance

    def execute(self, system_prompt: str, message: str) -> str:
        return self._get_executor().execute(system_prompt, message)
