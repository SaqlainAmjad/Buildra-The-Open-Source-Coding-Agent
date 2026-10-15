"""edit_file: exact-match search and replace inside one file.

The model sends a snippet copied from the file (``old_string``) and its
replacement. Requiring an *exact, unique* match is what makes this safe: if
the model misremembers the code, the edit fails loudly instead of changing
the wrong place. (opencode adds fuzzy fallbacks for whitespace mistakes;
those are on Buildra's roadmap.)
"""

from pydantic import BaseModel, Field

from buildra.tools.base import Tool, ToolContext, ToolError, ToolResult
from buildra.tools.text_files import read_text, unified_diff, write_text


class EditFileArgs(BaseModel):
    """Arguments for the edit_file tool."""

    path: str = Field(description="File path, relative to the working directory or absolute.")
    old_string: str = Field(description="Exact text to replace, copied from the file.")
    new_string: str = Field(description="Replacement text.")
    replace_all: bool = Field(default=False, description="Replace every occurrence.")


class EditFileTool(Tool[EditFileArgs]):
    """Exact string replacement that preserves the file's line endings."""

    name = "edit_file"
    description = (
        "Replace an exact snippet in an existing file. old_string must match the file "
        "exactly (including indentation) and be unique unless replace_all is true; include "
        "a few surrounding lines to make it unique. Do not include read_file's line-number "
        "prefixes. Use write_file to create new files."
    )
    args_model = EditFileArgs

    def summary(self, args: EditFileArgs) -> str:
        """Describe the call."""
        return args.path

    def run(self, args: EditFileArgs, ctx: ToolContext) -> ToolResult:
        """Apply the replacement or explain precisely why it cannot be applied."""
        if not args.old_string:
            raise ToolError(
                "old_string is empty. Use write_file to create or replace a whole file."
            )
        if args.old_string == args.new_string:
            raise ToolError("old_string and new_string are identical; nothing to change.")

        path = ctx.path(args.path)
        shown = ctx.workspace.display(path)
        before = read_text(path, shown)
        old, new = _match_line_endings(before, args.old_string, args.new_string)

        count = before.count(old)
        if count == 0:
            raise ToolError(
                f"old_string was not found in {shown}. It must match exactly, including "
                "whitespace and indentation. Re-read the file with read_file and copy the text."
            )
        if count > 1 and not args.replace_all:
            raise ToolError(
                f"old_string occurs {count} times in {shown}. Include more surrounding lines "
                "to make it unique, or set replace_all to true."
            )

        after = before.replace(old, new) if args.replace_all else before.replace(old, new, 1)
        write_text(path, after)
        replaced = count if args.replace_all else 1
        return ToolResult(
            output=f"Edited {shown}: replaced {replaced} occurrence{'s' * (replaced != 1)}.",
            display=unified_diff(before, after, shown),
        )


def _match_line_endings(content: str, old: str, new: str) -> tuple[str, str]:
    """Models write LF line endings; convert to CRLF when the file uses Windows endings."""
    if "\r\n" not in content:
        return old, new
    return (
        old.replace("\r\n", "\n").replace("\n", "\r\n"),
        new.replace("\r\n", "\n").replace("\n", "\r\n"),
    )
