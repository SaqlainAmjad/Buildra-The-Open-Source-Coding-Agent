from typing import Any

from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.graph import END

from buildra.agent.history import steps_since_user, unanswered_tool_messages
from buildra.agent.routing import route_after_agent, route_after_tools
from fakes import ai, call


def state(*messages: Any, **extra: Any) -> Any:
    return {"messages": list(messages), **extra}


def test_route_to_authorize_when_tools_requested() -> None:
    assert (
        route_after_agent(state(HumanMessage("hi"), ai("", call("glob", pattern="*"))))
        == "authorize"
    )


def test_route_to_end_on_plain_answer() -> None:
    assert route_after_agent(state(HumanMessage("hi"), ai("hello"))) == END


def test_route_back_to_agent_after_tools() -> None:
    decisions = {
        "c1": {"action": "run", "message": ""},
        "c2": {"action": "invalid", "message": "x"},
    }

    assert route_after_tools(state(decisions=decisions)) == "agent"


def test_rejection_ends_turn_but_correction_continues() -> None:
    rejected = {"c1": {"action": "rejected", "message": "no"}}
    corrected = {"c1": {"action": "corrected", "message": "do y"}}

    assert route_after_tools(state(decisions=rejected)) == END
    assert route_after_tools(state(decisions=corrected)) == "agent"


def test_steps_count_model_replies_since_last_user_message() -> None:
    messages = [HumanMessage("1"), ai("a"), HumanMessage("2"), ai("", call("glob")), ai("b")]

    assert steps_since_user(messages) == 2


def test_unanswered_tool_calls_are_closed() -> None:
    messages = [
        HumanMessage("go"),
        ai("", call("glob", call_id="done"), call("bash", call_id="open")),
        ToolMessage("result", tool_call_id="done"),
    ]

    [closing] = unanswered_tool_messages(messages, "Cancelled by the user.")

    assert closing.tool_call_id == "open"
    assert closing.content == "Cancelled by the user."
