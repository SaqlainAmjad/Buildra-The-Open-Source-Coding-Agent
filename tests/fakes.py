"""Test doubles shared across the test suite."""

from collections.abc import Sequence
from pathlib import Path
from typing import Any, ClassVar

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from pydantic import BaseModel, Field

from buildra.agent import AgentContext
from buildra.config.schema import AgentSettings, Settings
from buildra.permissions.sandbox import Workspace
from buildra.tools import Tool, ToolContext, ToolRegistry, ToolResult, default_registry


class ScriptedChatModel(BaseChatModel):
    """Returns pre-written replies in order and records every request it receives."""

    replies: list[AIMessage]
    requests: list[list[BaseMessage]] = Field(default_factory=list)
    bind_kwargs: list[dict[str, Any]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools: Sequence[Any], **kwargs: Any) -> "ScriptedChatModel":  # type: ignore[override]
        self.bind_kwargs.append(kwargs)
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: CallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.requests.append(list(messages))
        if not self.replies:
            raise AssertionError("ScriptedChatModel ran out of replies")
        return ChatResult(generations=[ChatGeneration(message=self.replies.pop(0))])


def call(name: str, call_id: str = "c1", **args: Any) -> dict[str, Any]:
    """A tool call dict as it appears in ``AIMessage.tool_calls``."""
    return {"name": name, "args": args, "id": call_id, "type": "tool_call"}


def ai(text: str = "", *calls: dict[str, Any], **extra: Any) -> AIMessage:
    """An assistant message with optional tool calls."""
    return AIMessage(content=text, tool_calls=list(calls), **extra)


class CounterArgs(BaseModel):
    """Arguments for the counter tool."""

    label: str = "x"


class CounterTool(Tool[CounterArgs]):
    """A side-effecting tool that counts how often it really ran."""

    name = "counter"
    description = "Increment a counter."
    args_model = CounterArgs
    runs: ClassVar[list[str]] = []

    def summary(self, args: CounterArgs) -> str:
        return f"count {args.label}"

    def run(self, args: CounterArgs, ctx: ToolContext) -> ToolResult:
        CounterTool.runs.append(args.label)
        return ToolResult(f"counted {args.label}")


def make_context(
    root: Path,
    model: ScriptedChatModel,
    *,
    max_steps: int = 10,
    registry: ToolRegistry | None = None,
) -> AgentContext:
    """An AgentContext over ``root`` with the scripted model."""
    return AgentContext(
        settings=Settings(agent=AgentSettings(max_steps=max_steps)),
        llm=model,
        model_id="scripted/test",
        tools=registry or default_registry(),
        workspace=Workspace(root),
    )
