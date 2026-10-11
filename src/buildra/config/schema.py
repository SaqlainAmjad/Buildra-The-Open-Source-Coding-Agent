"""The settings schema.

Every option Buildra understands is declared here with its default, so this
file doubles as the configuration reference. Unknown keys are rejected
(``extra="forbid"``) so a typo in a config file fails loudly instead of being
silently ignored.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Reasoning = Literal["off", "low", "high", "max"]
"""Provider-neutral reasoning ("thinking") level; each provider maps it to its own API."""


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProviderSettings(_Strict):
    """Connection overrides for one provider; unset fields use the provider's defaults."""

    base_url: str | None = None
    api_key_env: str | None = Field(
        default=None,
        description="Name of the environment variable holding the API key.",
    )


class LLMSettings(_Strict):
    """Which model to call and how."""

    model: str = Field(
        default="deepseek/deepseek-flash",
        description='Model id in "provider/model" form.',
    )
    reasoning: Reasoning = "off"
    temperature: float | None = None
    max_retries: int = Field(default=3, ge=0, le=10)
    request_timeout_s: float = Field(default=120.0, gt=0)
    providers: dict[str, ProviderSettings] = Field(default_factory=dict)


class AgentSettings(_Strict):
    """Limits on the agent loop."""

    max_steps: int = Field(default=50, ge=1, description="Model calls allowed per user turn.")


class ToolSettings(_Strict):
    """Limits applied to tool execution and tool output."""

    output_max_lines: int = Field(default=2000, ge=10)
    output_max_bytes: int = Field(default=50 * 1024, ge=1024)
    shell_timeout_s: float = Field(default=120.0, gt=0)
    shell_max_timeout_s: float = Field(default=600.0, gt=0)


class Settings(_Strict):
    """All Buildra settings."""

    llm: LLMSettings = Field(default_factory=LLMSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    tools: ToolSettings = Field(default_factory=ToolSettings)
