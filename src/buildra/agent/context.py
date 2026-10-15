"""Runtime context: per-run dependencies that are injected, never checkpointed.

LangGraph passes this to nodes as ``runtime.context``. Because the model is
injected here, tests can swap in a scripted fake model and run the whole
graph offline.
"""

from dataclasses import dataclass

from langchain_core.language_models import BaseChatModel

from buildra.config.schema import Settings
from buildra.permissions.sandbox import Workspace
from buildra.tools import ToolContext, ToolRegistry


@dataclass(frozen=True)
class AgentContext:
    """Services available to every node."""

    settings: Settings
    llm: BaseChatModel
    model_id: str
    tools: ToolRegistry
    workspace: Workspace

    def tool_context(self) -> ToolContext:
        """The narrower context handed to tools."""
        return ToolContext(workspace=self.workspace, settings=self.settings.tools)
