"""The contract every tool implements.

A tool is a typed function the model can call: a Pydantic model describes
its arguments (and becomes the JSON schema sent to the model), ``run`` does
the work, and the result has separate text for the model and for the user.
Idea from opencode's ``tool/tool.ts``, re-expressed with Pydantic.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar, Generic, TypeVar

from pydantic import BaseModel

from buildra.config.schema import ToolSettings
from buildra.permissions.sandbox import OutsideWorkspaceError, Workspace


class ToolError(Exception):
    """An expected failure the model should read and react to (file missing, no match...)."""


@dataclass(frozen=True)
class ToolContext:
    """What a running tool may use: the workspace and the tool limits."""

    workspace: Workspace
    settings: ToolSettings

    def path(self, raw: str) -> Path:
        """Resolve a model-supplied path, rejecting anything outside the workspace."""
        try:
            return self.workspace.resolve_inside(raw)
        except OutsideWorkspaceError as error:
            raise ToolError(
                f"{error} Access outside the workspace is not allowed. "
                "Use a path inside the working directory."
            ) from error


@dataclass(frozen=True)
class ToolResult:
    """Outcome of a successful tool run.

    ``output`` is what the model sees. ``display`` is optional richer text for
    the terminal (for example a diff) that would only waste model context.
    """

    output: str
    display: str | None = None


ArgsT = TypeVar("ArgsT", bound=BaseModel)


class Tool(ABC, Generic[ArgsT]):
    """Base class for tools. Subclasses set the class attributes and implement ``run``."""

    name: ClassVar[str]
    description: ClassVar[str]
    args_model: type[ArgsT]
    read_only: ClassVar[bool] = False
    """Read-only tools never change anything, so they run without asking the user."""

    @abstractmethod
    def run(self, args: ArgsT, ctx: ToolContext) -> ToolResult:
        """Execute the tool. Raise :class:`ToolError` for failures the model should see."""

    @abstractmethod
    def summary(self, args: ArgsT) -> str:
        """One line describing this call for the terminal and approval prompts."""

    def parse(self, raw: dict[str, Any]) -> ArgsT:
        """Validate raw model arguments (raises ``pydantic.ValidationError``)."""
        return self.args_model.model_validate(raw)

    def schema(self) -> dict[str, Any]:
        """Return the OpenAI-style function schema passed to ``bind_tools``."""
        parameters = self.args_model.model_json_schema()
        parameters.pop("title", None)  # Pydantic adds the class name and docstring;
        parameters.pop("description", None)  # the function description already covers them.
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": parameters,
            },
        }
