"""list_dir: an indented tree of a directory, skipping ignored entries."""

from pathlib import Path

from pydantic import BaseModel, Field

from buildra.tools.base import Tool, ToolContext, ToolError, ToolResult
from buildra.tools.ignore import IgnoreRules

MAX_ENTRIES = 500


class ListDirArgs(BaseModel):
    """Arguments for the list_dir tool."""

    path: str = Field(default=".", description="Directory to list (default: working directory).")
    depth: int = Field(default=2, ge=1, le=5, description="How many levels deep to list.")


class ListDirTool(Tool[ListDirArgs]):
    """Directory tree with folders marked by a trailing slash."""

    name = "list_dir"
    description = (
        "List a directory as an indented tree (folders end with '/'). Skips .git, "
        "node_modules, virtualenvs and .gitignore'd files. Use depth to see further down."
    )
    args_model = ListDirArgs
    read_only = True

    def summary(self, args: ListDirArgs) -> str:
        """Describe the call."""
        return args.path

    def run(self, args: ListDirArgs, ctx: ToolContext) -> ToolResult:
        """Build the tree breadth-limited by ``depth`` and capped at ``MAX_ENTRIES``."""
        root = ctx.path(args.path)
        if not root.is_dir():
            raise ToolError(f"Not a directory: {ctx.workspace.display(root)}")
        rules = IgnoreRules.load(ctx.workspace.root)
        rows: list[str] = []
        total = _collect(root, rules, args.depth, 0, rows)
        header = f"{ctx.workspace.display(root)}/"
        body = "\n".join(rows) if rows else "  (empty)"
        footer = f"\n... ({total - len(rows)} more entries not shown)" if total > len(rows) else ""
        return ToolResult(f"{header}\n{body}{footer}")


def _collect(folder: Path, rules: IgnoreRules, depth: int, level: int, rows: list[str]) -> int:
    """Append tree rows for ``folder``; return how many entries exist (shown or not)."""
    try:
        entries = sorted(folder.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
    except PermissionError:
        rows.append(f"{'  ' * (level + 1)}(permission denied)")
        return 1
    total = 0
    for entry in entries:
        is_dir = entry.is_dir()
        if rules.is_ignored(entry, is_dir=is_dir):
            continue
        total += 1
        if len(rows) < MAX_ENTRIES:
            rows.append(f"{'  ' * (level + 1)}{entry.name}{'/' if is_dir else ''}")
        if is_dir and level + 1 < depth:
            total += _collect(entry, rules, depth, level + 1, rows)
    return total
