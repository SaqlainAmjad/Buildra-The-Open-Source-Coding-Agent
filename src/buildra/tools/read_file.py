"""read_file: show a text file with line numbers, one page at a time."""

from pydantic import BaseModel, Field

from buildra.tools.base import Tool, ToolContext, ToolResult
from buildra.tools.text_files import read_text

MAX_LINE_CHARS = 2000


class ReadFileArgs(BaseModel):
    """Arguments for the read_file tool."""

    path: str = Field(description="File path, relative to the working directory or absolute.")
    offset: int = Field(default=1, ge=1, description="1-based line number to start from.")
    limit: int = Field(default=2000, ge=1, le=2000, description="Maximum lines to return.")


class ReadFileTool(Tool[ReadFileArgs]):
    """Paged, line-numbered file reading (paging rules from opencode ``read.ts``)."""

    name = "read_file"
    description = (
        "Read a text file. Output lines are prefixed with their line number and a colon, "
        'e.g. "12: text"; the prefix is NOT part of the file. Long files are returned in '
        "pages: use offset and limit to read further. Read a file before editing it."
    )
    args_model = ReadFileArgs
    read_only = True

    def summary(self, args: ReadFileArgs) -> str:
        """Describe the call."""
        return args.path if args.offset == 1 else f"{args.path} (from line {args.offset})"

    def run(self, args: ReadFileArgs, ctx: ToolContext) -> ToolResult:
        """Return one page of the file, stopping early to respect the byte budget."""
        path = ctx.path(args.path)
        shown = ctx.workspace.display(path)
        lines = read_text(path, shown).splitlines()
        if not lines:
            return ToolResult(f"({shown} is empty.)")
        if args.offset > len(lines):
            return ToolResult(
                f"({shown} has only {len(lines)} lines; offset {args.offset} is past the end.)"
            )

        budget = ctx.settings.output_max_bytes - 512  # leave room for the footer
        out: list[str] = []
        used = 0
        last = args.offset - 1
        for number in range(args.offset, min(len(lines), args.offset + args.limit - 1) + 1):
            text = lines[number - 1]
            if len(text) > MAX_LINE_CHARS:
                text = text[:MAX_LINE_CHARS] + f"... (line truncated to {MAX_LINE_CHARS} chars)"
            row = f"{number}: {text}"
            used += len(row.encode("utf-8")) + 1
            if out and used > budget:
                break
            out.append(row)
            last = number

        footer = (
            f"(End of file: {len(lines)} lines.)"
            if last >= len(lines)
            else f"(Showing lines {args.offset}-{last} of {len(lines)}. "
            f"Use offset={last + 1} to read more.)"
        )
        return ToolResult("\n".join(out) + "\n\n" + footer)
