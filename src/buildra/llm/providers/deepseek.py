"""DeepSeek adapter (OpenAI-compatible API at https://api.deepseek.com).

Notes from the DeepSeek API reference (checked 2026-10):

- Current models: ``deepseek-flash`` and ``deepseek-v4-pro`` (1M context,
  tool calls supported).
- *Thinking mode is on by default.* It is switched with the request field
  ``thinking: {"type": "enabled" | "disabled", "reasoning_effort": ...}``,
  which the OpenAI SDK does not know about, so it goes in ``extra_body``.
- In thinking mode, forced ``tool_choice`` (``required`` or a named tool) is
  rejected with HTTP 400. Buildra only uses ``auto``.
- ``ChatDeepSeek`` stores streamed ``reasoning_content`` in
  ``additional_kwargs`` but does not send it back on later requests.
"""

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_deepseek import ChatDeepSeek

from buildra.config.schema import Reasoning
from buildra.llm.providers.base import ModelRequest


class DeepSeekAdapter:
    """Creates :class:`ChatDeepSeek` models."""

    name = "deepseek"
    default_api_key_env = "DEEPSEEK_API_KEY"

    def create(self, request: ModelRequest) -> BaseChatModel:
        """Build a streaming-ready DeepSeek chat model."""
        options: dict[str, Any] = {
            "model": request.model,
            "api_key": request.api_key,
            "max_retries": request.max_retries,
            "timeout": request.timeout_s,
            "temperature": request.temperature,
            # Report token usage while streaming; context management needs it.
            "stream_usage": True,
            "extra_body": {"thinking": thinking_payload(request.reasoning)},
        }
        if request.base_url:
            options["api_base"] = request.base_url
        return ChatDeepSeek(**options)


def thinking_payload(reasoning: Reasoning) -> dict[str, str]:
    """Translate Buildra's reasoning level into DeepSeek's ``thinking`` field."""
    if reasoning == "off":
        return {"type": "disabled"}
    return {"type": "enabled", "reasoning_effort": reasoning}
