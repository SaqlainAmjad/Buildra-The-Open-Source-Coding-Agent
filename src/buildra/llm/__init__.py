"""Provider-agnostic access to chat models.

The rest of Buildra only sees LangChain's ``BaseChatModel`` interface
(``bind_tools``, ``invoke``, ``stream``). Everything provider-specific lives
in ``llm/providers/``, so adding OpenAI, Anthropic or Gemini means adding one
module there and registering it in ``registry.py``.
"""

from buildra.llm.errors import LLMConfigError
from buildra.llm.model_ref import ModelRef
from buildra.llm.registry import available_providers, create_chat_model

__all__ = ["LLMConfigError", "ModelRef", "available_providers", "create_chat_model"]
