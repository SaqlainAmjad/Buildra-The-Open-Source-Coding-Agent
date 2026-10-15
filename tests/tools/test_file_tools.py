from pathlib import Path

import pytest

from buildra.tools import ToolContext, ToolError
from buildra.tools.edit_file import EditFileArgs, EditFileTool
from buildra.tools.list_dir import ListDirArgs, ListDirTool
from buildra.tools.read_file import ReadFileArgs, ReadFileTool
from buildra.tools.write_file import WriteFileArgs, WriteFileTool

# ------------------------------------------------------------------ read_file


def test_read_numbers_lines_and_reports_end(ctx: ToolContext, workspace: Path) -> None:
    (workspace / "a.txt").write_text("one\ntwo\n")

    out = ReadFileTool().run(ReadFileArgs(path="a.txt"), ctx).output

    assert out.startswith("1: one\n2: two")
    assert "End of file: 2 lines" in out


def test_read_pages_with_offset_hint(ctx: ToolContext, workspace: Path) -> None:
    (workspace / "big.txt").write_text("".join(f"l{i}\n" for i in range(1, 11)))

    out = ReadFileTool().run(ReadFileArgs(path="big.txt", offset=3, limit=2), ctx).output

    assert out.startswith("3: l3\n4: l4")
    assert "Use offset=5" in out


def test_read_missing_file_suggests_search(ctx: ToolContext) -> None:
    with pytest.raises(ToolError, match="glob or list_dir"):
        ReadFileTool().run(ReadFileArgs(path="nope.txt"), ctx)


def test_read_rejects_binary(ctx: ToolContext, workspace: Path) -> None:
    (workspace / "img.bin").write_bytes(b"\x89PNG\x00\x00data")

    with pytest.raises(ToolError, match="binary"):
        ReadFileTool().run(ReadFileArgs(path="img.bin"), ctx)


def test_read_outside_workspace_is_refused(ctx: ToolContext) -> None:
    with pytest.raises(ToolError, match="outside the workspace"):
        ReadFileTool().run(ReadFileArgs(path="../secret.txt"), ctx)


# ------------------------------------------------------------------ write_file


def test_write_creates_parents_and_reports(ctx: ToolContext, workspace: Path) -> None:
    result = WriteFileTool().run(WriteFileArgs(path="src/new.py", content="x = 1\n"), ctx)

    assert (workspace / "src" / "new.py").read_text() == "x = 1\n"
    assert result.output == "Created src/new.py (1 lines)."
    assert result.display is not None and "+x = 1" in result.display


def test_write_overwrites(ctx: ToolContext, workspace: Path) -> None:
    (workspace / "f.txt").write_text("old\n")

    result = WriteFileTool().run(WriteFileArgs(path="f.txt", content="new\n"), ctx)

    assert result.output.startswith("Overwrote f.txt")
    assert (workspace / "f.txt").read_text() == "new\n"


# ------------------------------------------------------------------ edit_file


def test_edit_replaces_unique_match(ctx: ToolContext, workspace: Path) -> None:
    (workspace / "m.py").write_text("def f():\n    return 1\n")

    result = EditFileTool().run(
        EditFileArgs(path="m.py", old_string="return 1", new_string="return 2"), ctx
    )

    assert (workspace / "m.py").read_text() == "def f():\n    return 2\n"
    assert result.output == "Edited m.py: replaced 1 occurrence."
    assert result.display is not None and "-    return 1" in result.display


def test_edit_not_found_tells_model_to_reread(ctx: ToolContext, workspace: Path) -> None:
    (workspace / "m.py").write_text("x = 1\n")

    with pytest.raises(ToolError, match="Re-read the file"):
        EditFileTool().run(EditFileArgs(path="m.py", old_string="y = 1", new_string="y = 2"), ctx)


def test_edit_ambiguous_match_requires_context(ctx: ToolContext, workspace: Path) -> None:
    (workspace / "m.py").write_text("a = 0\na = 0\n")

    with pytest.raises(ToolError, match="occurs 2 times"):
        EditFileTool().run(EditFileArgs(path="m.py", old_string="a = 0", new_string="a = 1"), ctx)


def test_edit_replace_all(ctx: ToolContext, workspace: Path) -> None:
    (workspace / "m.py").write_text("a = 0\na = 0\n")

    result = EditFileTool().run(
        EditFileArgs(path="m.py", old_string="a = 0", new_string="a = 1", replace_all=True), ctx
    )

    assert (workspace / "m.py").read_text() == "a = 1\na = 1\n"
    assert "2 occurrences" in result.output


def test_edit_preserves_crlf(ctx: ToolContext, workspace: Path) -> None:
    (workspace / "w.txt").write_bytes(b"first\r\nsecond\r\n")

    EditFileTool().run(
        EditFileArgs(path="w.txt", old_string="first\nsecond", new_string="1st\n2nd"), ctx
    )

    assert (workspace / "w.txt").read_bytes() == b"1st\r\n2nd\r\n"


def test_edit_rejects_empty_old_string(ctx: ToolContext, workspace: Path) -> None:
    (workspace / "m.py").write_text("x\n")

    with pytest.raises(ToolError, match="write_file"):
        EditFileTool().run(EditFileArgs(path="m.py", old_string="", new_string="y"), ctx)


# ------------------------------------------------------------------ list_dir


def test_list_dir_tree_skips_ignored(ctx: ToolContext, workspace: Path) -> None:
    (workspace / "src").mkdir()
    (workspace / "src" / "app.py").write_text("")
    (workspace / "node_modules").mkdir()
    (workspace / "node_modules" / "pkg.js").write_text("")
    (workspace / "build.log").write_text("")
    (workspace / ".gitignore").write_text("*.log\n")

    out = ListDirTool().run(ListDirArgs(), ctx).output

    assert "src/" in out and "app.py" in out
    assert "node_modules" not in out
    assert "build.log" not in out


def test_list_dir_depth_limits_nesting(ctx: ToolContext, workspace: Path) -> None:
    (workspace / "a" / "b").mkdir(parents=True)
    (workspace / "a" / "b" / "deep.txt").write_text("")

    out = ListDirTool().run(ListDirArgs(depth=1), ctx).output

    assert "a/" in out
    assert "deep.txt" not in out
