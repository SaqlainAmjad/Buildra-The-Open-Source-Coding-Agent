"""The ``agent`` node: one call to the model (the "Reason" in ReAct).

Tokens stream to the terminal on their own: when the graph is run with
``stream_mode="messages"``, LangGraph hooks into the model's callbacks and
forwards each chunk, even though this node just calls ``invoke``.
"""

from typing import Any

from langchain_core.messages import AnyMessage, HumanMessage, SystemMessage
from langgraph.runtime import Runtime

from buildra.agent.context import AgentContext
from buildra.agent.history import steps_since_user
from buildra.agent.state import AgentState
from buildra.agent.system_prompt import build_system_prompt

FINAL_STEP_NOTE = (
    "<system-reminder>You have reached the maximum number of steps for this turn. Do not "
    "call any more tools. Tell the user what you did, what is left, and how to continue."
    "</system-reminder>"
)


def agent_node(state: AgentState, runtime: Runtime[AgentContext]) -> dict[str, Any]:
    """Ask the model for its next message, with tools bound unless the budget is spent."""
    ctx = runtime.context
    history = state["messages"]
    messages: list[AnyMessage] = [SystemMessage(build_system_prompt(ctx)), *history]

    if steps_since_user(history) >= ctx.settings.agent.max_steps:
        # Out of steps: keep tool schemas (the history mentions them) but forbid new
        # calls, so the turn ends with a summary instead of being cut off mid-task.
        model = ctx.llm.bind_tools(ctx.tools.schemas(), tool_choice="none")
        messages.append(HumanMessage(FINAL_STEP_NOTE))
    else:
        model = ctx.llm.bind_tools(ctx.tools.schemas())

    return {"messages": [model.invoke(messages)]}
