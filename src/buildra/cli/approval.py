"""Ask the user to approve tool calls in the terminal."""

from collections.abc import Callable

from rich.console import Console
from rich.text import Text

from buildra.agent.approval import ApprovalAnswer, ApprovalAnswers, ApprovalPrompt


class ConsoleApprover:
    """Implements :class:`~buildra.cli.turn.Approver`.

    Answers: ``y`` runs the call, ``n`` (or Enter) declines it, any other text
    declines it and passes the text to the model as instructions.
    """

    def __init__(self, console: Console, read_line: Callable[[str], str] = input) -> None:
        """Prompt on ``console``; ``read_line`` is injectable for tests."""
        self.console = console
        self.read_line = read_line

    def decide(self, prompt: ApprovalPrompt) -> ApprovalAnswers:
        """Ask about each request in turn."""
        answers: ApprovalAnswers = {}
        for request in prompt["requests"]:
            self.console.print(
                Text.assemble(
                    ("? ", "bold yellow"),
                    ("Allow ", "yellow"),
                    (request["tool"], "bold yellow"),
                    "  ",
                    request["summary"],
                )
            )
            answers[request["call_id"]] = parse_answer(self._read())
        return answers

    def _read(self) -> str:
        try:
            return self.read_line("  [y]es / [n]o / or type instructions: ")
        except EOFError:  # no terminal (piped input ran out): decline, never auto-approve
            return ""


def parse_answer(raw: str) -> ApprovalAnswer:
    """Map what the user typed to an answer. Empty input counts as no (safe default)."""
    text = raw.replace("﻿", "").strip()  # piped input on Windows may start with a BOM
    if text.lower() in {"y", "yes"}:
        return {"approved": True, "feedback": None}
    if text.lower() in {"", "n", "no"}:
        return {"approved": False, "feedback": None}
    return {"approved": False, "feedback": text}
