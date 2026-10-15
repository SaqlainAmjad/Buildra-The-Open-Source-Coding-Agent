"""The workspace boundary: resolve model-supplied paths and check containment.

Every path a tool receives comes from the model, so it is untrusted. We
resolve it fully (``~`` expansion, ``..`` segments, symlinks) *before*
checking it, otherwise ``src/../../secrets`` or a symlink pointing outside
would slip through a naive string-prefix check.
"""

from pathlib import Path


class OutsideWorkspaceError(Exception):
    """A path resolves outside the workspace root."""

    def __init__(self, path: Path, root: Path) -> None:
        super().__init__(f"{path} is outside the workspace ({root}).")
        self.path = path
        self.root = root


class Workspace:
    """The directory the agent works in; all relative paths resolve against it."""

    def __init__(self, root: Path) -> None:
        """Create a workspace rooted at ``root`` (resolved to an absolute path)."""
        self.root = root.expanduser().resolve()

    def resolve(self, raw: str) -> Path:
        """Turn a model-supplied path into an absolute, normalised path."""
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = self.root / path
        return path.resolve()

    def contains(self, path: Path) -> bool:
        """Return whether an already-resolved ``path`` lies inside the workspace."""
        return path == self.root or path.is_relative_to(self.root)

    def resolve_inside(self, raw: str) -> Path:
        """Resolve ``raw`` and require it to stay inside the workspace.

        Raises:
            OutsideWorkspaceError: If the resolved path escapes the root.
        """
        path = self.resolve(raw)
        if not self.contains(path):
            raise OutsideWorkspaceError(path, self.root)
        return path

    def display(self, path: Path) -> str:
        """Return ``path`` relative to the root (POSIX style) when inside, else absolute."""
        if self.contains(path):
            relative = path.relative_to(self.root).as_posix()
            return relative or "."
        return str(path)
