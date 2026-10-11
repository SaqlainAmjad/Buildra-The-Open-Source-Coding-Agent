"""Model identifiers of the form ``provider/model``.

Borrowed from opencode, which addresses every model as ``providerID/modelID``
(for example ``anthropic/claude-sonnet-4``). The provider part selects the
adapter; the model part is passed to that provider's API unchanged.
"""

from dataclasses import dataclass

from buildra.llm.errors import LLMConfigError


@dataclass(frozen=True)
class ModelRef:
    """A parsed ``provider/model`` id."""

    provider: str
    model: str

    @classmethod
    def parse(cls, text: str) -> "ModelRef":
        """Parse ``"provider/model"``; the model part may itself contain slashes.

        Raises:
            LLMConfigError: If either part is missing.
        """
        provider, sep, model = text.strip().partition("/")
        if not sep or not provider or not model:
            raise LLMConfigError(
                f'Invalid model id "{text}". Use "provider/model", e.g. "deepseek/deepseek-flash".'
            )
        return cls(provider=provider.lower(), model=model)

    def __str__(self) -> str:
        return f"{self.provider}/{self.model}"
