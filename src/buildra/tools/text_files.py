"""Read and write workspace text files with errors the model can act on."""

import difflib
from pathlib import Path

from buildra.tools.base import ToolError

_BINARY_SNIFF_BYTES = 8192


def looks_binary(data: bytes) -> bool:
    """Heuristic used by git and ripgrep: a NUL byte near the start means binary."""
    return b"\x00" in data[:_BINARY_SNIFF_BYTES]


def read_text(path: Path, shown: str) -> str:
    """Return the file's text exactly as stored (line endings preserved).

    Args:
        path: Absolute path to read.
        shown: How to name the file in error messages.

    Raises:
        ToolError: Missing file, a directory, binary content or invalid UTF-8.
    """
    if path.is_dir():
        raise ToolError(f"{shown} is a directory. Use list_dir to see its contents.")
    if not path.is_file():
        raise ToolError(f"File not found: {shown}. Use glob or list_dir to find the right path.")
    data = path.read_bytes()
    if looks_binary(data):
        raise ToolError(f"{shown} looks like a binary file; only text files can be read.")
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as error:
        raise ToolError(f"{shown} is not valid UTF-8 text ({error.reason}).") from error


def write_text(path: Path, text: str) -> None:
    """Write ``text`` byte-for-byte (no newline translation), creating parent folders."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as file:
        file.write(text)


def unified_diff(before: str, after: str, label: str) -> str:
    """Return a unified diff of two versions of a file, for display."""
    lines = difflib.unified_diff(
        before.splitlines(keepends=True),
        after.splitlines(keepends=True),
        fromfile=f"a/{label}",
        tofile=f"b/{label}",
    )
    return "".join(line if line.endswith("\n") else line + "\n" for line in lines)


def count_lines(text: str) -> int:
    """Number of lines as an editor would show them."""
    return len(text.splitlines())
