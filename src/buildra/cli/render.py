"""Terminal rendering with rich: streamed text, tool calls, results and diffs."""

from langchain_core.messages import ToolMessage
from rich.console import Console
from rich.syntax import Syntax
from rich.text import Text

PREVIEW_LINES = 6
DIFF_LINES = 80


class ConsoleView:
    """Implements :class:`~buildra.cli.turn.TurnView` on a rich console."""

    def __init__(self, console: Console) -> None:
        """Render to ``console``."""
        self.console = console
        self._mid_line = False  # did we print streamed text without a newline yet?
        self._mode: str | None = None  # "text" or "reasoning" while streaming

    def text(self, chunk: str) -> None:
        """Print answer tokens as they arrive."""
        self._switch("text")
        self._write(chunk, style=None)

    def reasoning(self, chunk: str) -> None:
        """Print reasoning tokens dimmed so they read as asides."""
        self._switch("reasoning")
        self._write(chunk, style="dim italic")

    def tool_start(self, tool: str, summary: str) -> None:
        """Show which tool runs, e.g. ``> bash  pytest -q``."""
        self._break_line()
        line = Text.assemble(
            ("> ", "cyan"), (tool, "bold cyan"), "  ", (_one_line(summary), "white")
        )
        self.console.print(line)

    def tool_result(self, message: ToolMessage) -> None:
        """Show a short preview of the result, or the diff for file changes."""
        self._break_line()
        content = str(message.content)
        if message.status == "error":
            self.console.print(Text(f"  x {_first_line(content)}", style="red"))
            return
        display = (
            (message.artifact or {}).get("display") if isinstance(message.artifact, dict) else None
        )
        if display:
            self.console.print(Syntax(_head(display, DIFF_LINES), "diff", theme="ansi_dark"))
            return
        self.console.print(Text(_indent(_head(content, PREVIEW_LINES)), style="dim"))

    def pause(self) -> None:
        """End a half-printed line so an approval prompt starts cleanly."""
        self._break_line()

    def end_of_turn(self) -> None:
        """Finish the current line and leave a blank line before the next prompt."""
        self._break_line()
        self._mode = None
        self.console.print()

    def info(self, message: str) -> None:
        """A neutral status message."""
        self._break_line()
        self.console.print(Text(message, style="dim"))

    def error(self, message: str) -> None:
        """An error the user should see."""
        self._break_line()
        self.console.print(Text(message, style="bold red"))

    def _switch(self, mode: str) -> None:
        if self._mode != mode:
            self._break_line()
            self._mode = mode

    def _write(self, chunk: str, style: str | None) -> None:
        self.console.print(Text(chunk, style=style or ""), end="", soft_wrap=True)
        self._mid_line = not chunk.endswith("\n")

    def _break_line(self) -> None:
        if self._mid_line:
            self.console.print()
            self._mid_line = False
        self._mode = None


def _head(text: str, lines: int) -> str:
    rows = text.rstrip("\n").splitlines()
    if len(rows) <= lines:
        return "\n".join(rows)
    return "\n".join([*rows[:lines], f"... ({len(rows) - lines} more lines)"])


def _indent(text: str) -> str:
    return "\n".join(f"  {row}" for row in text.splitlines())


def _first_line(text: str) -> str:
    return text.strip().splitlines()[0] if text.strip() else "(error)"


def _one_line(text: str, limit: int = 120) -> str:
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 3] + "..."
