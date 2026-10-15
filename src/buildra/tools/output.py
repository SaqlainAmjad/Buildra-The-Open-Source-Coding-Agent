"""Bound tool output before it enters the model's context.

One ``cat`` of a log file can be bigger than the whole context window, so
every tool result is capped. Like opencode (``tool/truncate.ts``) we keep the
*beginning and the end*: errors usually show up at the end of command output,
while headers and structure are at the start.
"""

from collections.abc import Sequence


def truncate(text: str, *, max_lines: int, max_bytes: int) -> str:
    """Return ``text`` unchanged if within limits, else its head and tail with a marker."""
    lines = text.splitlines(keepends=True)
    if len(lines) <= max_lines and _size(text) <= max_bytes:
        return text

    head = _take(lines, max_lines // 2, max_bytes // 2)
    rest = lines[len(head) :]
    tail = _take(rest[::-1], max_lines - max_lines // 2, max_bytes // 2, from_end=True)[::-1]
    omitted = len(lines) - len(head) - len(tail)
    marker = (
        f"\n... [{omitted} lines omitted: output exceeded {max_lines} lines or "
        f"{max_bytes // 1024} KB. Narrow the command or read a smaller range.] ...\n"
    )
    return "".join(head).rstrip("\n") + marker + "".join(tail)


def _take(
    lines: Sequence[str], max_count: int, budget: int, *, from_end: bool = False
) -> list[str]:
    taken: list[str] = []
    used = 0
    for line in lines[:max_count]:
        size = _size(line)
        if used + size > budget:
            if not taken:  # a single huge line (minified file): keep a clipped piece
                taken.append(_clip(line, budget, from_end=from_end))
            break
        taken.append(line)
        used += size
    return taken


def _clip(line: str, budget: int, *, from_end: bool) -> str:
    data = line.encode("utf-8")
    piece = data[-budget:] if from_end else data[:budget]
    return piece.decode("utf-8", errors="ignore")


def _size(text: str) -> int:
    return len(text.encode("utf-8"))
