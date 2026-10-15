"""Which files the search and listing tools skip.

Without this, ``glob("**/*.js")`` in a web project would walk all of
``node_modules`` and drown the model in vendored code. We skip well-known
junk directories and honour the workspace's root ``.gitignore``.
"""

import os
from collections.abc import Iterator
from pathlib import Path

import pathspec

ALWAYS_IGNORED_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
    }
)


class IgnoreRules:
    """Ignore decisions for one workspace root."""

    def __init__(self, root: Path, gitignore: pathspec.GitIgnoreSpec | None = None) -> None:
        """Create rules for ``root`` with an optional parsed ``.gitignore``."""
        self.root = root
        self._spec = gitignore

    @classmethod
    def load(cls, root: Path) -> "IgnoreRules":
        """Read ``<root>/.gitignore`` if present."""
        gitignore = root / ".gitignore"
        if not gitignore.is_file():
            return cls(root)
        lines = gitignore.read_text(encoding="utf-8", errors="replace").splitlines()
        return cls(root, pathspec.GitIgnoreSpec.from_lines(lines))

    def is_ignored(self, path: Path, *, is_dir: bool) -> bool:
        """Return whether ``path`` (absolute) should be skipped."""
        if is_dir and path.name in ALWAYS_IGNORED_DIRS:
            return True
        if self._spec is None or not path.is_relative_to(self.root) or path == self.root:
            return False
        relative = path.relative_to(self.root).as_posix() + ("/" if is_dir else "")
        return self._spec.match_file(relative)

    def walk_files(self, start: Path) -> Iterator[Path]:
        """Yield files under ``start`` in sorted order, pruning ignored directories."""
        for current, dirs, files in os.walk(start):
            base = Path(current)
            dirs[:] = sorted(d for d in dirs if not self.is_ignored(base / d, is_dir=True))
            for name in sorted(files):
                path = base / name
                if not self.is_ignored(path, is_dir=False):
                    yield path
