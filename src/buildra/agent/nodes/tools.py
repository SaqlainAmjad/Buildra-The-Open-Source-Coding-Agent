"""The ``tools`` node: execute approved calls (the "Act" in ReAct).

Every tool call id in the model's message gets exactly one ``ToolMessage``,
whether it ran, failed, was invalid or was declined. Providers reject a
history where a tool call has no matching result.

This node never calls ``interrupt()``, so its side effects run exactly once.
"""

import logging
from typing import Any

from langchain_core.messages import ToolMessage
from langgraph.config import get_stream_writer
from langgraph.runtime import Runtime

from buildra.agent.context import AgentContext
from buildra.agent.history import last_ai_message
from buildra.agent.state import AgentState, Decision
from buildra.tools import InvalidToolCall, PreparedCall, ToolContext, ToolError
from buildra.tools.output import truncate

logger = logging.getLogger(__name__)

_MISSING: Decision = {"action": "invalid", "message": "This tool call was not authorized."}


def tools_node(state: AgentState, runtime: Runtime[AgentContext]) -> dict[str, Any]:
    """Run each authorized call in order and return one ToolMessage per call id."""
    ctx = runtime.context
    message = last_ai_message(state["messages"])
    decisions = state.get("decisions", {})
    emit = get_stream_writer()
    results: list[ToolMessage] = []

    def finish(result: ToolMessage) -> None:
        # Stream each result as soon as it exists; the node's update only arrives at the end.
        results.append(result)
        emit({"event": "tool_end", "message": result})

    for call in message.tool_calls:
        call_id = call["id"] or ""
        decision = decisions.get(call_id, _MISSING)
        if decision["action"] != "run":
            finish(_refusal(call_id, call["name"], decision))
            continue
        try:
            prepared = ctx.tools.prepare(call["name"], call["args"])
        except InvalidToolCall as error:  # only if the registry changed mid-turn
            finish(_refusal(call_id, call["name"], {"action": "invalid", "message": str(error)}))
            continue
        emit({"event": "tool_start", "tool": call["name"], "summary": prepared.summary()})
        finish(_execute(prepared, call_id, ctx.tool_context()))

    for malformed in message.invalid_tool_calls:
        call_id = malformed["id"] or ""
        finish(_refusal(call_id, malformed["name"] or "", decisions.get(call_id, _MISSING)))

    return {"messages": results}


def _execute(call: PreparedCall, call_id: str, ctx: ToolContext) -> ToolMessage:
    name = call.tool.name
    try:
        result = call.tool.run(call.args, ctx)
    except ToolError as error:
        return _message(call_id, name, f"Error: {error}", status="error")
    except Exception as error:  # a bug in a tool must not crash the whole session
        logger.exception("Tool %s crashed", name)
        return _message(
            call_id,
            name,
            f"Internal error in {name}: {type(error).__name__}: {error}",
            status="error",
        )
    output = truncate(
        result.output,
        max_lines=ctx.settings.output_max_lines,
        max_bytes=ctx.settings.output_max_bytes,
    )
    return _message(call_id, name, output, status="success", display=result.display)


def _refusal(call_id: str, name: str, decision: Decision) -> ToolMessage:
    return _message(call_id, name, decision["message"], status="error")


def _message(
    call_id: str, name: str, content: str, *, status: str, display: str | None = None
) -> ToolMessage:
    # ``artifact`` travels with the message for the UI but is never sent to the model.
    return ToolMessage(
        content=content,
        tool_call_id=call_id,
        name=name,
        status=status,
        artifact={"display": display} if display else None,
    )
