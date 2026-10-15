"""powershell: run a PowerShell command (registered on Windows only)."""

import shutil
from pathlib import Path

from pydantic import BaseModel, Field

from buildra.tools.base import Tool, ToolContext, ToolResult
from buildra.tools.process import describe_outcome, effective_timeout, run_command

# Windows PowerShell 5.1 writes output in the console's legacy code page; force UTF-8.
_UTF8_PREAMBLE = "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "


class PowerShellArgs(BaseModel):
    """Arguments for the powershell tool."""

    command: str = Field(description="The PowerShell command to run in the working directory.")
    timeout_s: float | None = Field(
        default=None, gt=0, description="Timeout in seconds (default 120, maximum 600)."
    )


class PowerShellTool(Tool[PowerShellArgs]):
    """Non-interactive PowerShell for Windows-specific work."""

    name = "powershell"
    description = (
        "Run a PowerShell command in the working directory and return its output and exit "
        "code. Use it for Windows-specific tasks (registry, services, .ps1 scripts, Windows "
        "paths); use bash for everything else. Commands cannot read input."
    )
    args_model = PowerShellArgs

    def __init__(self, executable: Path) -> None:
        """Use the PowerShell binary at ``executable``."""
        self.executable = executable

    def summary(self, args: PowerShellArgs) -> str:
        """Describe the call."""
        return args.command

    def run(self, args: PowerShellArgs, ctx: ToolContext) -> ToolResult:
        """Run the command and report output plus exit status."""
        timeout = effective_timeout(
            args.timeout_s, ctx.settings.shell_timeout_s, ctx.settings.shell_max_timeout_s
        )
        argv = [
            str(self.executable),
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            _UTF8_PREAMBLE + args.command,
        ]
        outcome = run_command(argv, cwd=ctx.workspace.root, timeout_s=timeout)
        return ToolResult(describe_outcome(outcome, timeout))


def find_powershell() -> Path | None:
    """Prefer PowerShell 7 (``pwsh``), fall back to Windows PowerShell."""
    for name in ("pwsh", "powershell"):
        if found := shutil.which(name):
            return Path(found)
    return None
