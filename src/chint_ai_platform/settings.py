"""Environment-backed application settings."""

import os
from collections.abc import Mapping
from dataclasses import dataclass


class DeepSeekNotConfiguredError(RuntimeError):
    """Raised when the DeepSeek API credential is unavailable."""


@dataclass(frozen=True)
class DeepSeekSettings:
    """Configuration required to create a DeepSeek client."""

    api_key: str
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-v4-flash"

    @classmethod
    def from_environment(
        cls,
        environ: Mapping[str, str] | None = None,
    ) -> "DeepSeekSettings":
        values = os.environ if environ is None else environ
        api_key = values.get("DEEPSEEK_API_KEY", "").strip()
        if not api_key:
            raise DeepSeekNotConfiguredError("DeepSeek API key is not configured")
        return cls(
            api_key=api_key,
            base_url=values.get("DEEPSEEK_BASE_URL", cls.base_url),
            model=values.get("DEEPSEEK_MODEL", cls.model),
        )
