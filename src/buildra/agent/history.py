"""Pure helpers that read the message history.

Providers require a well-formed history: every tool call in an assistant
message must be followed by a tool message with the same id. These helpers
find the pieces the nodes need and repair a history that an interruption
(Ctrl+C) left half-finished.
"""

from collections.abc import Sequence

from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, ToolMessage


def last_ai_message(messages: Sequence[AnyMessage]) -> AIMessage:
    """Return the final message, which the graph guarantees is the model's reply."""
    last = messages[-1] if messages else None
    if not isinstance(last, AIMessage):
        raise ValueError("Expected the last message to be an AIMessage.")
    return last


def wants_tools(message: AnyMessage) -> bool:
    """Whether the model asked for any tool call, well-formed or not."""
    return isinstance(message, AIMessage) and bool(message.tool_calls or message.invalid_tool_calls)


def steps_since_user(messages: Sequence[AnyMessage]) -> int:
    """Count model replies since the latest user message (the step budget per turn)."""
    count = 0
    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            break
        if isinstance(message, AIMessage):
            count += 1
    return count


def unanswered_tool_messages(messages: Sequence[AnyMessage], reason: str) -> list[ToolMessage]:
    """Tool messages that close any tool calls left without a result.

    Used after the user cancels mid-turn, so the next request is still valid.
    """
    answered = {m.tool_call_id for m in messages if isinstance(m, ToolMessage)}
    closing: list[ToolMessage] = []
    for message in messages:
        if not isinstance(message, AIMessage):
            continue
        calls: list[tuple[str | None, str | None]] = [
            (c.get("id"), c.get("name")) for c in message.tool_calls
        ]
        calls += [(c.get("id"), c.get("name")) for c in message.invalid_tool_calls]
        closing += [
            ToolMessage(reason, tool_call_id=call_id, name=name or "", status="error")
            for call_id, name in calls
            if call_id and call_id not in answered
        ]
    return closing
