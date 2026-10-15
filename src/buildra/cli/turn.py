"""Drive the graph through one user turn: stream, pause for approvals, resume.

This is the only module that knows how LangGraph streams. Output goes to a
:class:`TurnView` and approvals come from an :class:`Approver`, both
protocols, so the loop is tested without a terminal.

Streaming uses ``graph.stream(..., stream_mode=[...], version="v2")``; each
chunk is ``{"type": mode, "ns": ..., "data": ...}``:

- ``messages``: ``(message_chunk, metadata)`` as the model generates tokens
- ``custom``: events our nodes emit with ``get_stream_writer()``: ``tool_start``
  before a tool runs and ``tool_end`` with its ToolMessage right after. (The
  ``updates`` mode would only deliver results once the whole tools node ends,
  so parallel calls would show all starts first and all results last.)
"""

from typing import Any, Protocol

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Command

from buildra.agent.approval import ApprovalAnswers, ApprovalPrompt
from buildra.agent.context import AgentContext
from buildra.agent.graph import AgentGraph, recursion_limit
from buildra.agent.history import unanswered_tool_messages
from buildra.agent.state import AgentState

STREAM_MODES: Any = ["messages", "custom"]
CANCELLED = "The user cancelled this tool call before it finished."

TurnInput = AgentState | Command[Any]
"""A new user message, or a resume value after an interrupt."""


class TurnView(Protocol):
    """Where a turn's output goes."""

    def text(self, chunk: str) -> None:
        """A piece of the model's answer."""

    def reasoning(self, chunk: str) -> None:
        """A piece of the model's reasoning (thinking mode)."""

    def tool_start(self, tool: str, summary: str) -> None:
        """A tool is about to run."""

    def tool_result(self, message: ToolMessage) -> None:
        """A tool call finished (or was refused)."""

    def pause(self) -> None:
        """The turn waits for the user (an approval); finish any partial output line."""

    def end_of_turn(self) -> None:
        """The turn is complete."""


class Approver(Protocol):
    """Answers approval prompts raised by the graph."""

    def decide(self, prompt: ApprovalPrompt) -> ApprovalAnswers:
        """Return an answer for every request in ``prompt``."""


class TurnRunner:
    """Runs turns on one conversation thread."""

    def __init__(
        self,
        graph: AgentGraph,
        context: AgentContext,
        view: TurnView,
        approver: Approver,
        thread_id: str,
    ) -> None:
        """Bind the runner to a graph, its dependencies and a thread."""
        self.graph = graph
        self.context = context
        self.view = view
        self.approver = approver
        self.config: RunnableConfig = {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": recursion_limit(context.settings.agent.max_steps),
        }

    def run(self, user_text: str) -> None:
        """Send ``user_text`` and keep resuming until the graph finishes."""
        payload: TurnInput = {"messages": [HumanMessage(user_text)]}
        while True:
            self._stream(payload)
            interrupts = self.graph.get_state(self.config).interrupts
            if not interrupts:
                break
            prompt: ApprovalPrompt = interrupts[0].value
            self.view.pause()
            payload = Command(resume=self.approver.decide(prompt))
        self.view.end_of_turn()

    def cancel(self) -> None:
        """Repair history after Ctrl+C so the next request is valid.

        Any tool call left without a result gets a "cancelled" tool message;
        a pending approval is abandoned. The next user message starts fresh.
        """
        snapshot = self.graph.get_state(self.config)
        messages = snapshot.values.get("messages", [])
        closing = unanswered_tool_messages(messages, CANCELLED)
        if closing:
            self.graph.update_state(self.config, {"messages": closing}, as_node="tools")

    def _stream(self, payload: TurnInput) -> None:
        for chunk in self.graph.stream(
            payload, self.config, context=self.context, stream_mode=STREAM_MODES, version="v2"
        ):
            # The chunk type is a union over every stream mode; we branch on "type" ourselves.
            kind, data = chunk["type"], chunk["data"]
            payload_data: Any = data
            if kind == "messages":
                self._on_message(*payload_data)
            elif kind == "custom" and payload_data.get("event") == "tool_start":
                self.view.tool_start(payload_data["tool"], payload_data["summary"])
            elif kind == "custom" and payload_data.get("event") == "tool_end":
                self.view.tool_result(payload_data["message"])

    def _on_message(self, message: object, metadata: dict[str, Any]) -> None:
        if metadata.get("langgraph_node") != "agent" or not isinstance(message, AIMessage):
            return
        if reasoning := message.additional_kwargs.get("reasoning_content"):
            self.view.reasoning(str(reasoning))
        if isinstance(message.content, str) and message.content:
            self.view.text(message.content)
