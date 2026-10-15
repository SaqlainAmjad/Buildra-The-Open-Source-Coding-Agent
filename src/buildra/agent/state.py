"""Graph state: everything that belongs to the conversation and is checkpointed.

Keep this small. Services (the model, the tool registry, settings) are not
state; they live in :class:`~buildra.agent.context.AgentContext`.
"""

from typing import Annotated, Literal, NotRequired, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages

DecisionAction = Literal["run", "invalid", "rejected", "corrected"]
"""What happens to one tool call.

- ``run``: execute it.
- ``invalid``: unknown tool or bad arguments; send the error back so the model retries.
- ``rejected``: the user said no; send a refusal and end the turn.
- ``corrected``: the user said no *with instructions*; send them and let the model continue.
"""


class Decision(TypedDict):
    """The ``authorize`` node's verdict for one tool call id."""

    action: DecisionAction
    message: str
    """Text returned to the model instead of running the tool (empty for ``run``)."""


class AgentState(TypedDict):
    """State of one conversation thread."""

    messages: Annotated[list[AnyMessage], add_messages]
    """Full history. ``add_messages`` appends new messages (or replaces by id)."""

    decisions: NotRequired[dict[str, Decision]]
    """Hand-off from ``authorize`` to ``tools`` for the latest tool calls."""
