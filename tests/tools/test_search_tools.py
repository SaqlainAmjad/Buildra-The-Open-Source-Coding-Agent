import os
from pathlib import Path

import pytest

from buildra.tools import ToolContext, ToolError
from buildra.tools.glob import GlobArgs, GlobTool
from buildra.tools.grep import GrepArgs, GrepTool


@pytest.fixture
def project(workspace: Path) -> Path:
    (workspace / "src").mkdir()
    (workspace / "src" / "main.py").write_text("def main():\n    print('hello')\n")
    (workspace / "src" / "util.ts").write_text("export const hello = 1\n")
    (workspace / "README.md").write_text("Hello project\n")
    (workspace / "node_modules").mkdir()
    (workspace / "node_modules" / "dep.py").write_text("print('hello')\n")
    return workspace


def test_glob_matches_at_any_depth_and_skips_ignored(ctx: ToolContext, project: Path) -> None:
    out = GlobTool().run(GlobArgs(pattern="*.py"), ctx).output

    assert out.splitlines() == ["src/main.py"]


def test_glob_sorts_newest_first(ctx: ToolContext, project: Path) -> None:
    os.utime(project / "README.md", (1, 1))  # make README the oldest

    out = GlobTool().run(GlobArgs(pattern="*"), ctx).output.splitlines()

    assert out[-1] == "README.md"


def test_glob_no_match(ctx: ToolContext, project: Path) -> None:
    assert "No files match" in GlobTool().run(GlobArgs(pattern="*.rs"), ctx).output


def test_grep_reports_path_line_text(ctx: ToolContext, project: Path) -> None:
    out = GrepTool().run(GrepArgs(pattern=r"print\("), ctx).output

    assert out == "src/main.py:2: print('hello')"


def test_grep_include_and_ignore_case(ctx: ToolContext, project: Path) -> None:
    out = GrepTool().run(GrepArgs(pattern="hello", include="*.md", ignore_case=True), ctx).output

    assert out == "README.md:1: Hello project"


def test_grep_invalid_regex_is_explained(ctx: ToolContext, project: Path) -> None:
    with pytest.raises(ToolError, match="Invalid regular expression"):
        GrepTool().run(GrepArgs(pattern="("), ctx)


def test_grep_skips_binary(ctx: ToolContext, project: Path) -> None:
    (project / "blob.bin").write_bytes(b"hello\x00world")

    out = GrepTool().run(GrepArgs(pattern="hello"), ctx).output

    assert "blob.bin" not in out
