from pathlib import Path

import pytest

from buildra.permissions.sandbox import OutsideWorkspaceError, Workspace


def test_relative_paths_resolve_against_root(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)

    assert ws.resolve("src/app.py") == tmp_path.resolve() / "src" / "app.py"


def test_dot_dot_escape_is_rejected(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "project")

    with pytest.raises(OutsideWorkspaceError):
        ws.resolve_inside("src/../../secrets.txt")


def test_absolute_path_outside_is_rejected(tmp_path: Path) -> None:
    ws = Workspace(tmp_path / "project")

    with pytest.raises(OutsideWorkspaceError):
        ws.resolve_inside(str(tmp_path / "other" / "file.txt"))


def test_root_itself_is_inside(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)

    assert ws.resolve_inside(".") == tmp_path.resolve()
    assert ws.display(tmp_path.resolve()) == "."


def test_display_is_relative_posix(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)

    assert ws.display(tmp_path.resolve() / "a" / "b.txt") == "a/b.txt"


def test_symlink_pointing_outside_is_rejected(tmp_path: Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = project / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("creating symlinks needs extra privileges on this platform")

    with pytest.raises(OutsideWorkspaceError):
        Workspace(project).resolve_inside("escape/file.txt")
