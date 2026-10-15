"""Assemble the agent graph. Nodes and edges only; the logic lives in nodes/ and routing.py.

::

    START -> agent --(no tool calls)--------------------------> END
               ^ |
               | +--(tool calls)--> authorize --> tools --(declined)--> END
               |                                    |
               +------------------------------------+
"""

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from buildra.agent.context import AgentContext
from buildra.agent.nodes.agent import agent_node
from buildra.agent.nodes.authorize import authorize_node
from buildra.agent.nodes.tools import tools_node
from buildra.agent.routing import route_after_agent, route_after_tools
from buildra.agent.state import AgentState

AgentGraph = CompiledStateGraph[AgentState, AgentContext, AgentState, AgentState]


def build_graph(checkpointer: BaseCheckpointSaver[str] | None = None) -> AgentGraph:
    """Compile the ReAct graph. A checkpointer is required for approvals (interrupts)."""
    builder = StateGraph(AgentState, context_schema=AgentContext)
    builder.add_node("agent", agent_node)
    builder.add_node("authorize", authorize_node)
    builder.add_node("tools", tools_node)

    builder.add_edge(START, "agent")
    builder.add_conditional_edges("agent", route_after_agent, ["authorize", END])
    builder.add_edge("authorize", "tools")
    builder.add_conditional_edges("tools", route_after_tools, ["agent", END])
    return builder.compile(checkpointer=checkpointer)


def recursion_limit(max_steps: int) -> int:
    """LangGraph's super-step cap for one run: 3 nodes per step, plus the final answer."""
    return max_steps * 3 + 5
