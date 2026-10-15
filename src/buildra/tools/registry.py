"""Look up tools by name and turn raw model tool calls into validated calls.

Validation errors are phrased *for the model*: the message becomes the tool
result, the model reads it on its next step and fixes the call. This is the
"validate, then let the model retry" loop from opencode's
``InvalidArgumentsError`` (``tool/tool.ts``).
"""

import sys
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from buildra.tools.base import Tool


class InvalidToolCall(Exception):
    """A tool call the model must re-issue; the message tells it how."""


@dataclass(frozen=True)
class PreparedCall:
    """A tool call whose name resolved and whose arguments validated."""

    tool: Tool[Any]
    args: Any

    def summary(self) -> str:
        """One-line description of the call."""
        return self.tool.summary(self.args)


class ToolRegistry:
    """The set of tools offered to the model."""

    def __init__(self, tools: Iterable[Tool[Any]]) -> None:
        """Register ``tools``; names must be unique."""
        self._tools: dict[str, Tool[Any]] = {}
        for tool in tools:
            if tool.name in self._tools:
                raise ValueError(f"Duplicate tool name: {tool.name}")
            self._tools[tool.name] = tool

    def names(self) -> list[str]:
        """Return registered tool names in registration order."""
        return list(self._tools)

    def get(self, name: str) -> Tool[Any] | None:
        """Return the tool called ``name``, if any."""
        return self._tools.get(name)

    def schemas(self) -> list[dict[str, Any]]:
        """Return function schemas for ``bind_tools``."""
        return [tool.schema() for tool in self._tools.values()]

    def prepare(self, name: str, raw_args: dict[str, Any]) -> PreparedCall:
        """Resolve and validate one tool call.

        Raises:
            InvalidToolCall: Unknown tool or arguments that fail the schema.
        """
        tool = self._tools.get(name)
        if tool is None:
            raise InvalidToolCall(
                f'Unknown tool "{name}". Available tools: {", ".join(self._tools)}.'
            )
        try:
            return PreparedCall(tool=tool, args=tool.parse(raw_args))
        except ValidationError as error:
            raise InvalidToolCall(_describe(name, error)) from error


def malformed_arguments_message(name: str | None, error: str | None) -> str:
    """Model-facing text for a call whose arguments were not even valid JSON."""
    detail = f": {error}" if error else ""
    return (
        f"The arguments for your call to {name or 'a tool'} were not valid JSON{detail}. "
        "Re-issue the call with a valid JSON object."
    )


def default_registry() -> ToolRegistry:
    """Return the built-in tools available on this platform."""
    from buildra.tools.bash import BashTool, find_bash
    from buildra.tools.edit_file import EditFileTool
    from buildra.tools.glob import GlobTool
    from buildra.tools.grep import GrepTool
    from buildra.tools.list_dir import ListDirTool
    from buildra.tools.powershell import PowerShellTool, find_powershell
    from buildra.tools.read_file import ReadFileTool
    from buildra.tools.write_file import WriteFileTool

    tools: list[Tool[Any]] = [
        ReadFileTool(),
        ListDirTool(),
        GlobTool(),
        GrepTool(),
        EditFileTool(),
        WriteFileTool(),
    ]
    if bash := find_bash():
        tools.append(BashTool(bash))
    if sys.platform == "win32" and (powershell := find_powershell()):
        tools.append(PowerShellTool(powershell))
    return ToolRegistry(tools)


def _describe(name: str, error: ValidationError) -> str:
    problems = "; ".join(
        f"{'.'.join(str(p) for p in item['loc']) or 'arguments'}: {item['msg']}"
        for item in error.errors()
    )
    return (
        f"The {name} tool was called with invalid arguments: {problems}. "
        "Rewrite the call so it matches the tool's schema."
    )
