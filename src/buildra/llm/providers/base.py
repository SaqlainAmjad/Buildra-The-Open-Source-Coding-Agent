"""The contract every provider adapter implements."""

from dataclasses import dataclass
from typing import Protocol

from langchain_core.language_models import BaseChatModel
from pydantic import SecretStr

from buildra.config.schema import Reasoning


@dataclass(frozen=True)
class ModelRequest:
    """Provider-neutral options for building a chat model.

    The registry resolves these from settings (including the API key from the
    environment) so provider modules never read config or ``os.environ``.
    """

    model: str
    api_key: SecretStr
    base_url: str | None
    reasoning: Reasoning
    temperature: float | None
    max_retries: int
    timeout_s: float


class ProviderAdapter(Protocol):
    """Builds LangChain chat models for one provider."""

    name: str
    """Provider id used in model refs, e.g. ``"deepseek"``."""

    default_api_key_env: str
    """Environment variable read for the API key unless config overrides it."""

    def create(self, request: ModelRequest) -> BaseChatModel:
        """Return a chat model that supports tool calling and token streaming."""
        ...
