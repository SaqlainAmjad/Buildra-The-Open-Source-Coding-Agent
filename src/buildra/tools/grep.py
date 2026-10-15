"""grep: search file contents with a regular expression."""

import re
from collections.abc import Iterator
from pathlib import Path

from pydantic import BaseModel, Field

from buildra.tools.base import Tool, ToolContext, ToolError, ToolResult
from buildra.tools.glob import compile_pattern
from buildra.tools.ignore import IgnoreRules
from buildra.tools.text_files import looks_binary

MAX_MATCHES = 200
MAX_FILE_BYTES = 1024 * 1024
MAX_MATCH_CHARS = 300


class GrepArgs(BaseModel):
    """Arguments for the grep tool."""

    pattern: str = Field(description="Python regular expression to search for.")
    path: str = Field(default=".", description="File or directory to search.")
    include: str | None = Field(
        default=None, description='Only search files matching this glob, e.g. "*.py".'
    )
    ignore_case: bool = Field(default=False, description="Case-insensitive matching.")


class GrepTool(Tool[GrepArgs]):
    """Regex search over text files, reporting ``path:line: text``."""

    name = "grep"
    description = (
        "Search file contents with a regular expression. Returns matching lines as "
        "'path:line: text'. Skips binary, very large and ignored files. Use include to "
        "restrict file types."
    )
    args_model = GrepArgs
    read_only = True

    def summary(self, args: GrepArgs) -> str:
        """Describe the call."""
        where = "" if args.path == "." else f" in {args.path}"
        return f"/{args.pattern}/{where}"

    def run(self, args: GrepArgs, ctx: ToolContext) -> ToolResult:
        """Collect up to ``MAX_MATCHES`` matching lines."""
        try:
            regex = re.compile(args.pattern, re.IGNORECASE if args.ignore_case else 0)
        except re.error as error:
            raise ToolError(f"Invalid regular expression {args.pattern!r}: {error}") from error

        start = ctx.path(args.path)
        if not start.exists():
            raise ToolError(f"Path not found: {ctx.workspace.display(start)}")
        matches: list[str] = []
        truncated = False
        for file, number, line in _search(regex, _candidates(start, args.include, ctx)):
            if len(matches) == MAX_MATCHES:
                truncated = True
                break
            text = line.strip()
            if len(text) > MAX_MATCH_CHARS:
                text = text[:MAX_MATCH_CHARS] + "..."
            matches.append(f"{ctx.workspace.display(file)}:{number}: {text}")

        if not matches:
            return ToolResult(f"No matches for {args.pattern!r}.")
        note = f"\n... (stopped at {MAX_MATCHES} matches; narrow the search)" if truncated else ""
        return ToolResult("\n".join(matches) + note)


def _candidates(start: Path, include: str | None, ctx: ToolContext) -> Iterator[Path]:
    if start.is_file():
        yield start
        return
    matcher = compile_pattern(include) if include else None
    for file in IgnoreRules.load(ctx.workspace.root).walk_files(start):
        if matcher is None or matcher.match_file(file.relative_to(start).as_posix()):
            yield file


def _search(regex: re.Pattern[str], files: Iterator[Path]) -> Iterator[tuple[Path, int, str]]:
    for file in files:
        try:
            if file.stat().st_size > MAX_FILE_BYTES:
                continue
            data = file.read_bytes()
        except OSError:
            continue
        if looks_binary(data):
            continue
        for number, line in enumerate(data.decode("utf-8", errors="replace").splitlines(), 1):
            if regex.search(line):
                yield file, number, line
