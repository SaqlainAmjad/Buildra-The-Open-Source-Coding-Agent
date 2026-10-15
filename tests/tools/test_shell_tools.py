import sys
from pathlib import Path

import pytest

from buildra.config.schema import ToolSettings
from buildra.permissions.sandbox import Workspace
from buildra.tools import ToolContext
from buildra.tools.bash import BashArgs, BashTool, find_bash
from buildra.tools.powershell import PowerShellArgs, PowerShellTool, find_powershell
from buildra.tools.process import effective_timeout, run_command

BASH = find_bash()
needs_bash = pytest.mark.skipif(BASH is None, reason="bash not available")


def test_timeout_is_clamped_to_maximum() -> None:
    assert effective_timeout(None, 120, 600) == 120
    assert effective_timeout(5000, 120, 600) == 600
    assert effective_timeout(3, 120, 600) == 3


@needs_bash
def test_bash_runs_in_workspace_and_reports_exit_code(ctx: ToolContext, workspace: Path) -> None:
    assert BASH is not None
    (workspace / "marker.txt").write_text("")

    out = BashTool(BASH).run(BashArgs(command="ls; exit 3"), ctx).output

    assert "marker.txt" in out
    assert out.endswith("[exit code 3]")


@needs_bash
def test_bash_merges_stderr(ctx: ToolContext) -> None:
    assert BASH is not None

    out = BashTool(BASH).run(BashArgs(command="echo oops >&2"), ctx).output

    assert "oops" in out


@needs_bash
def test_bash_timeout_kills_command(workspace: Path) -> None:
    assert BASH is not None
    fast = ToolContext(Workspace(workspace), ToolSettings(shell_timeout_s=1))

    out = BashTool(BASH).run(BashArgs(command="sleep 30"), fast).output

    assert "timeout" in out and "killed" in out


@needs_bash
def test_stdin_is_closed_so_prompts_do_not_hang(workspace: Path) -> None:
    assert BASH is not None

    outcome = run_command(
        [str(BASH), "-c", "read answer; echo got:$answer"], cwd=workspace, timeout_s=10
    )

    assert not outcome.timed_out
    assert "got:" in outcome.output


@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_powershell_runs_and_reports_exit_code(ctx: ToolContext) -> None:
    exe = find_powershell()
    assert exe is not None

    out = (
        PowerShellTool(exe).run(PowerShellArgs(command="Write-Output 'héllo'; exit 2"), ctx).output
    )

    assert "héllo" in out
    assert out.endswith("[exit code 2]")
