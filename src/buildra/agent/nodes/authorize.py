"""The ``authorize`` node: decide what happens to each tool call before anything runs.

Why this is its own node: ``interrupt()`` pauses the graph, and on resume
LangGraph re-runs the *whole node* from the top. This node has no side
effects (validation and policy are pure), so re-running it is harmless. If
approval lived inside the tool-running node, resuming would re-execute
commands that had already run.

v0.1 policy: read-only tools run freely, everything else asks the user.
Day 3 replaces ``_needs_approval`` with the allow / ask / deny rules engine.
"""

from typing import Any

from langchain_core.messages import InvalidToolCall as MalformedCall
from langchain_core.messages import ToolCall
from langgraph.runtime import Runtime
from langgraph.types import interrupt

from buildra.agent.approval import ApprovalAnswer, ApprovalAnswers, ApprovalPrompt, ApprovalRequest
from buildra.agent.context import AgentContext
from buildra.agent.history import last_ai_message
from buildra.agent.state import AgentState, Decision
from buildra.tools import InvalidToolCall, PreparedCall
from buildra.tools.registry import malformed_arguments_message

RUN: Decision = {"action": "run", "message": ""}


def authorize_node(state: AgentState, runtime: Runtime[AgentContext]) -> dict[str, Any]:
    """Validate every call, then ask the user once about all calls that need approval."""
    message = last_ai_message(state["messages"])
    decisions: dict[str, Decision] = {}
    pending: list[ApprovalRequest] = []

    for call in message.tool_calls:
        call_id = call["id"] or ""
        try:
            prepared = runtime.context.tools.prepare(call["name"], call["args"])
        except InvalidToolCall as error:
            decisions[call_id] = {"action": "invalid", "message": str(error)}
            continue
        if _needs_approval(prepared):
            pending.append(_request(call, prepared))
        else:
            decisions[call_id] = RUN

    for malformed in message.invalid_tool_calls:
        decisions[malformed["id"] or ""] = _malformed(malformed)

    if pending:
        # One interrupt per step keeps resume deterministic (interrupts match by order).
        answers: ApprovalAnswers = interrupt(ApprovalPrompt(kind="approval", requests=pending))
        for request in pending:
            decisions[request["call_id"]] = _from_answer(answers.get(request["call_id"]))

    return {"decisions": decisions}


def _needs_approval(call: PreparedCall) -> bool:
    return not call.tool.read_only


def _request(call: ToolCall, prepared: PreparedCall) -> ApprovalRequest:
    return {"call_id": call["id"] or "", "tool": call["name"], "summary": prepared.summary()}


def _malformed(call: MalformedCall) -> Decision:
    return {
        "action": "invalid",
        "message": malformed_arguments_message(call["name"], call["error"]),
    }


def _from_answer(answer: ApprovalAnswer | None) -> Decision:
    if answer and answer["approved"]:
        return RUN
    feedback = answer["feedback"] if answer else None
    if feedback:
        return {
            "action": "corrected",
            "message": f"The user declined this tool call and said: {feedback}",
        }
    return {
        "action": "rejected",
        "message": "The user declined this tool call. Wait for their next instruction.",
    }
