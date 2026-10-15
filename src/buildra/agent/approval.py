"""The approval protocol between the graph and whoever answers it (the CLI, a test...).

The ``authorize`` node calls ``interrupt(ApprovalPrompt)``; the caller shows
the requests and resumes the graph with ``Command(resume=ApprovalAnswers)``.
Both sides are plain JSON-friendly dicts because interrupt payloads and
resume values are stored in the checkpoint.
"""

from typing import TypedDict


class ApprovalRequest(TypedDict):
    """One tool call waiting for the user."""

    call_id: str
    tool: str
    summary: str


class ApprovalPrompt(TypedDict):
    """Interrupt payload: every call in this step that needs approval, asked at once."""

    kind: str  # always "approval"; lets callers recognise the payload type
    requests: list[ApprovalRequest]


class ApprovalAnswer(TypedDict):
    """The user's answer for one call."""

    approved: bool
    feedback: str | None
    """Optional instructions when declining ("use pytest -x instead")."""


ApprovalAnswers = dict[str, ApprovalAnswer]
"""Resume value: answers keyed by ``call_id``."""
