"""Assemble the system prompt sent at the start of every model call.

It is rebuilt on each call and never stored in the message history (the same
choice opencode makes in ``session/system.ts``). The content is kept stable
across calls: date but no clock time, no counters. Providers cache identical
prompt prefixes, and DeepSeek bills cache hits far below misses.
"""

import platform
import sys
from datetime import date
from importlib.resources import files

from buildra.agent.context import AgentContext

BASE_PROMPT = files("buildra.agent").joinpath("prompts", "system.md").read_text(encoding="utf-8")


def build_system_prompt(ctx: AgentContext, today: date | None = None) -> str:
    """Return the base instructions followed by an environment block."""
    return f"{BASE_PROMPT.rstrip()}\n\n{_environment(ctx, today or date.today())}"


def _environment(ctx: AgentContext, today: date) -> str:
    root = ctx.workspace.root
    shells = [name for name in ("bash", "powershell") if ctx.tools.get(name)]
    lines = [
        "<env>",
        f"Working directory: {root}",
        f"Git repository: {'yes' if (root / '.git').exists() else 'no'}",
        f"Platform: {sys.platform} ({platform.system()} {platform.release()})",
        f"Shell tools: {', '.join(shells) or 'none'}",
        f"Today's date: {today.isoformat()}",
        f"Model: {ctx.model_id}",
        "</env>",
    ]
    return "\n".join(lines)
