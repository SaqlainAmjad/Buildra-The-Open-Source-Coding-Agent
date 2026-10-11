"""Map provider ids to adapters and build chat models from settings."""

import os
from collections.abc import Mapping

from langchain_core.language_models import BaseChatModel
from pydantic import SecretStr

from buildra.config.schema import LLMSettings, ProviderSettings
from buildra.llm.errors import LLMConfigError
from buildra.llm.model_ref import ModelRef
from buildra.llm.providers.base import ModelRequest, ProviderAdapter
from buildra.llm.providers.deepseek import DeepSeekAdapter

_ADAPTERS: dict[str, ProviderAdapter] = {adapter.name: adapter for adapter in (DeepSeekAdapter(),)}


def available_providers() -> list[str]:
    """Return the provider ids Buildra can talk to."""
    return sorted(_ADAPTERS)


def create_chat_model(
    settings: LLMSettings,
    *,
    model: str | None = None,
    env: Mapping[str, str] | None = None,
) -> BaseChatModel:
    """Build the chat model selected by ``settings`` (or by ``model`` if given).

    Args:
        settings: The ``[llm]`` settings section.
        model: Optional ``provider/model`` id overriding ``settings.model``.
        env: Environment to read API keys from; defaults to ``os.environ``.

    Raises:
        LLMConfigError: Unknown provider, malformed model id or missing API key.
    """
    ref = ModelRef.parse(model or settings.model)
    adapter = _ADAPTERS.get(ref.provider)
    if adapter is None:
        raise LLMConfigError(
            f'Unknown provider "{ref.provider}". Available: {", ".join(available_providers())}.'
        )
    overrides = settings.providers.get(ref.provider, ProviderSettings())
    request = ModelRequest(
        model=ref.model,
        api_key=_api_key(overrides.api_key_env or adapter.default_api_key_env, env),
        base_url=overrides.base_url,
        reasoning=settings.reasoning,
        temperature=settings.temperature,
        max_retries=settings.max_retries,
        timeout_s=settings.request_timeout_s,
    )
    return adapter.create(request)


def _api_key(variable: str, env: Mapping[str, str] | None) -> SecretStr:
    value = (os.environ if env is None else env).get(variable, "").strip()
    if not value:
        raise LLMConfigError(
            f"{variable} is not set. Add it to your environment or to a .env file "
            "in the project directory (see .env.example)."
        )
    return SecretStr(value)
