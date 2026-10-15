"""Run a shell command with a hard timeout, shared by the bash and powershell tools.

Three things make agent-run commands safe to wait on:

- **stdin is closed**, so a command that prompts ("Continue? [y/N]") fails
  immediately instead of hanging forever;
- **pagers are disabled** (``git log`` would otherwise wait in ``less``);
- **the whole process tree is killed on timeout**, because killing only the
  shell leaves its children (a dev server, a test runner) running.
"""

import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CommandOutcome:
    """Result of one command run."""

    output: str
    exit_code: int | None
    timed_out: bool
    duration_s: float


def run_command(argv: list[str], *, cwd: Path, timeout_s: float) -> CommandOutcome:
    """Run ``argv`` in ``cwd`` with stdout and stderr merged, killing it after ``timeout_s``."""
    started = time.monotonic()
    # Start the command in its own process group so the whole tree can be killed.
    process = subprocess.Popen(  # noqa: S603 - argv is built by the shell tools, not a shell string
        argv,
        cwd=cwd,
        env=_environment(),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
        start_new_session=sys.platform != "win32",
    )
    try:
        raw, _ = process.communicate(timeout=timeout_s)
        timed_out = False
    except subprocess.TimeoutExpired:
        _kill_tree(process)
        raw, _ = process.communicate()
        timed_out = True
    return CommandOutcome(
        output=raw.decode("utf-8", errors="replace"),
        exit_code=None if timed_out else process.returncode,
        timed_out=timed_out,
        duration_s=time.monotonic() - started,
    )


def describe_outcome(outcome: CommandOutcome, timeout_s: float) -> str:
    """Format output plus a status line the model can reason about."""
    body = outcome.output.rstrip() or "(no output)"
    if outcome.timed_out:
        status = (
            f"[Command killed after exceeding the {timeout_s:g}s timeout. If it is expected to "
            "take longer and is not waiting for input, retry with a larger timeout_s.]"
        )
    else:
        status = f"[exit code {outcome.exit_code}]"
    return f"{body}\n{status}"


def effective_timeout(requested: float | None, default: float, maximum: float) -> float:
    """Clamp a model-requested timeout to the configured maximum."""
    return min(requested or default, maximum)


def _environment() -> dict[str, str]:
    env = dict(os.environ)
    env.update({"PAGER": "cat", "GIT_PAGER": "cat", "GIT_TERMINAL_PROMPT": "0"})
    return env


def _kill_tree(process: subprocess.Popen[bytes]) -> None:
    if sys.platform == "win32":
        subprocess.run(  # noqa: S603 - fixed system command
            ["taskkill", "/F", "/T", "/PID", str(process.pid)],  # noqa: S607 - system tool on PATH
            capture_output=True,
            check=False,
        )
    else:
        os.killpg(process.pid, signal.SIGKILL)
