"""Conditional edges: pure functions from state to the next node.

These replace the ``continue`` / ``break`` of opencode's ``while(true)`` loop
and are the easiest part of the agent to unit-test.
"""

from langgraph.graph import END

from buildra.agent.history import wants_tools
from buildra.agent.state import AgentState


def route_after_agent(state: AgentState) -> str:
    """Tools requested -> authorize them; plain answer -> the turn is over."""
    return "authorize" if wants_tools(state["messages"][-1]) else END


def route_after_tools(state: AgentState) -> str:
    """Back to the model with the results, unless the user declined a call outright."""
    decisions = state.get("decisions", {}).values()
    return END if any(d["action"] == "rejected" for d in decisions) else "agent"
