"""bash: run a command in a bash shell (Git Bash on Windows)."""

import shutil
import sys
from pathlib import Path

from pydantic import BaseModel, Field

from buildra.tools.base import Tool, ToolContext, ToolResult
from buildra.tools.process import describe_outcome, effective_timeout, run_command


class BashArgs(BaseModel):
    """Arguments for the bash tool."""

    command: str = Field(description="The bash command to run in the working directory.")
    timeout_s: float | None = Field(
        default=None, gt=0, description="Timeout in seconds (default 120, maximum 600)."
    )


class BashTool(Tool[BashArgs]):
    """Non-interactive bash commands with a timeout; output is stdout and stderr merged."""

    name = "bash"
    description = (
        "Run a bash command in the working directory and return its output and exit code. "
        "Use it for builds, tests, git and package managers. Commands cannot read input, "
        "so pass non-interactive flags (e.g. -y). Prefer read_file, glob and grep over "
        "cat, find and grep for reading and searching."
    )
    args_model = BashArgs

    def __init__(self, executable: Path) -> None:
        """Use the bash binary at ``executable``."""
        self.executable = executable

    def summary(self, args: BashArgs) -> str:
        """Describe the call."""
        return args.command

    def run(self, args: BashArgs, ctx: ToolContext) -> ToolResult:
        """Run the command and report output plus exit status."""
        timeout = effective_timeout(
            args.timeout_s, ctx.settings.shell_timeout_s, ctx.settings.shell_max_timeout_s
        )
        outcome = run_command(
            [str(self.executable), "-c", args.command], cwd=ctx.workspace.root, timeout_s=timeout
        )
        return ToolResult(describe_outcome(outcome, timeout))


def find_bash() -> Path | None:
    """Locate bash. On Windows prefer Git Bash, never the WSL launcher in System32."""
    if sys.platform != "win32":
        found = shutil.which("bash")
        return Path(found) if found else None
    for candidate in _windows_candidates():
        if candidate.is_file():
            return candidate
    return None


def _windows_candidates() -> list[Path]:
    candidates: list[Path] = []
    if git := shutil.which("git"):
        # .../Git/cmd/git.exe -> .../Git/bin/bash.exe
        candidates.append(Path(git).resolve().parent.parent / "bin" / "bash.exe")
    candidates += [
        Path(r"C:\Program Files\Git\bin\bash.exe"),
        Path(r"C:\Program Files (x86)\Git\bin\bash.exe"),
    ]
    if (found := shutil.which("bash")) and "system32" not in found.lower():
        candidates.append(Path(found))
    return candidates
