"""write_file: create a file or replace its whole content."""

from pydantic import BaseModel, Field

from buildra.tools.base import Tool, ToolContext, ToolResult
from buildra.tools.text_files import count_lines, read_text, unified_diff, write_text


class WriteFileArgs(BaseModel):
    """Arguments for the write_file tool."""

    path: str = Field(description="File path, relative to the working directory or absolute.")
    content: str = Field(description="The complete new file content.")


class WriteFileTool(Tool[WriteFileArgs]):
    """Whole-file writes; parent folders are created as needed."""

    name = "write_file"
    description = (
        "Create a new file or overwrite an existing one with the given content. "
        "Prefer edit_file for changing part of an existing file."
    )
    args_model = WriteFileArgs

    def summary(self, args: WriteFileArgs) -> str:
        """Describe the call."""
        return f"{args.path} ({count_lines(args.content)} lines)"

    def run(self, args: WriteFileArgs, ctx: ToolContext) -> ToolResult:
        """Write the file and report whether it was created or overwritten."""
        path = ctx.path(args.path)
        shown = ctx.workspace.display(path)
        existed = path.is_file()
        before = read_text(path, shown) if existed else ""
        write_text(path, args.content)
        verb = "Overwrote" if existed else "Created"
        return ToolResult(
            output=f"{verb} {shown} ({count_lines(args.content)} lines).",
            display=unified_diff(before, args.content, shown),
        )
