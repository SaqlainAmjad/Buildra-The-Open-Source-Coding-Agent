"""glob: find files by name pattern, newest first."""

import pathspec
from pydantic import BaseModel, Field

from buildra.tools.base import Tool, ToolContext, ToolError, ToolResult
from buildra.tools.ignore import IgnoreRules

MAX_RESULTS = 200


class GlobArgs(BaseModel):
    """Arguments for the glob tool."""

    pattern: str = Field(
        description='Gitignore-style pattern: "*.py" matches at any depth, "src/**/*.ts" '
        "only under src."
    )
    path: str = Field(default=".", description="Directory to search (default: working directory).")


class GlobTool(Tool[GlobArgs]):
    """File search by pattern, sorted by modification time (recent work first)."""

    name = "glob"
    description = (
        "Find files whose path matches a pattern. Results are paths relative to the working "
        "directory, most recently modified first. Ignored folders (node_modules, .git, "
        ".gitignore'd) are skipped."
    )
    args_model = GlobArgs
    read_only = True

    def summary(self, args: GlobArgs) -> str:
        """Describe the call."""
        return args.pattern if args.path == "." else f"{args.pattern} in {args.path}"

    def run(self, args: GlobArgs, ctx: ToolContext) -> ToolResult:
        """Walk the tree, match relative paths, and sort by recency."""
        start = ctx.path(args.path)
        if not start.is_dir():
            raise ToolError(f"Not a directory: {ctx.workspace.display(start)}")
        matcher = compile_pattern(args.pattern)
        rules = IgnoreRules.load(ctx.workspace.root)
        hits = [
            file
            for file in rules.walk_files(start)
            if matcher.match_file(file.relative_to(start).as_posix())
        ]
        if not hits:
            return ToolResult(f"No files match {args.pattern!r}.")
        hits.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        shown = [ctx.workspace.display(p) for p in hits[:MAX_RESULTS]]
        more = (
            f"\n... ({len(hits) - MAX_RESULTS} more; narrow the pattern)"
            if len(hits) > MAX_RESULTS
            else ""
        )
        return ToolResult("\n".join(shown) + more)


def compile_pattern(pattern: str) -> pathspec.GitIgnoreSpec:
    """Compile a gitignore-style pattern, with an error the model can act on."""
    try:
        return pathspec.GitIgnoreSpec.from_lines([pattern])
    except Exception as error:  # pathspec raises several error types for bad patterns
        raise ToolError(f"Invalid pattern {pattern!r}: {error}") from error
