"""End-to-end graph behaviour with a scripted model (no network)."""

from pathlib import Path
from typing import Any

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from buildra.agent import AgentContext, build_graph
from buildra.agent.nodes.agent import FINAL_STEP_NOTE
from buildra.tools import ToolRegistry, default_registry
from buildra.tools.read_file import ReadFileTool
from fakes import CounterTool, ScriptedChatModel, ai, call, make_context

CONFIG: Any = {"configurable": {"thread_id": "t1"}}


@pytest.fixture
def graph() -> Any:
    return build_graph(InMemorySaver())


def run(graph: Any, ctx: AgentContext, payload: Any) -> list[Any]:
    """Invoke the graph and return the messages of the resulting state."""
    graph.invoke(payload, CONFIG, context=ctx)
    return list(graph.get_state(CONFIG).values["messages"])


def ask(text: str) -> dict[str, Any]:
    return {"messages": [HumanMessage(text)]}


def tool_messages(messages: list[Any]) -> list[ToolMessage]:
    return [m for m in messages if isinstance(m, ToolMessage)]


def test_plain_answer_ends_the_turn(graph: Any, tmp_path: Path) -> None:
    model = ScriptedChatModel(replies=[ai("Hello!")])

    messages = run(graph, make_context(tmp_path, model), ask("hi"))

    assert [type(m) for m in messages] == [HumanMessage, AIMessage]
    assert messages[-1].content == "Hello!"
    assert len(model.requests) == 1


def test_system_prompt_is_sent_but_not_stored(graph: Any, tmp_path: Path) -> None:
    model = ScriptedChatModel(replies=[ai("ok")])

    messages = run(graph, make_context(tmp_path, model), ask("hi"))

    assert model.requests[0][0].type == "system"
    assert "<env>" in str(model.requests[0][0].content)
    assert all(m.type != "system" for m in messages)


def test_read_only_tool_runs_without_approval(graph: Any, tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("secret sauce\n")
    model = ScriptedChatModel(
        replies=[ai("", call("read_file", path="notes.txt")), ai("It says secret sauce.")]
    )

    messages = run(graph, make_context(tmp_path, model), ask("what is in notes.txt?"))

    [result] = tool_messages(messages)
    assert result.tool_call_id == "c1"
    assert "1: secret sauce" in str(result.content)
    assert result in model.requests[1]  # the model saw the result on its next step
    assert messages[-1].content == "It says secret sauce."


def test_write_waits_for_approval_then_runs(graph: Any, tmp_path: Path) -> None:
    model = ScriptedChatModel(
        replies=[ai("", call("write_file", path="out.txt", content="hi\n")), ai("Done.")]
    )
    ctx = make_context(tmp_path, model)

    run(graph, ctx, ask("create out.txt"))
    [pending] = graph.get_state(CONFIG).interrupts

    assert pending.value["requests"] == [
        {"call_id": "c1", "tool": "write_file", "summary": "out.txt (1 lines)"}
    ]
    assert not (tmp_path / "out.txt").exists()  # nothing happened before approval

    messages = run(graph, ctx, Command(resume={"c1": {"approved": True, "feedback": None}}))

    assert (tmp_path / "out.txt").read_text() == "hi\n"
    assert messages[-1].content == "Done."


def test_rejection_answers_the_call_and_ends_the_turn(graph: Any, tmp_path: Path) -> None:
    model = ScriptedChatModel(replies=[ai("", call("write_file", path="x.txt", content="x"))])
    ctx = make_context(tmp_path, model)

    run(graph, ctx, ask("write x"))
    messages = run(graph, ctx, Command(resume={"c1": {"approved": False, "feedback": None}}))

    [refusal] = tool_messages(messages)
    assert "declined" in str(refusal.content)
    assert refusal.status == "error"
    assert not (tmp_path / "x.txt").exists()
    assert len(model.requests) == 1  # the model was not called again
    assert graph.get_state(CONFIG).next == ()


def test_feedback_is_sent_to_the_model(graph: Any, tmp_path: Path) -> None:
    model = ScriptedChatModel(
        replies=[ai("", call("write_file", path="x.txt", content="x")), ai("Understood.")]
    )
    ctx = make_context(tmp_path, model)

    run(graph, ctx, ask("write x"))
    run(graph, ctx, Command(resume={"c1": {"approved": False, "feedback": "name it y.txt"}}))

    [refusal] = tool_messages(model.requests[1])
    assert "name it y.txt" in str(refusal.content)


def test_invalid_arguments_are_returned_for_self_correction(graph: Any, tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("A\n")
    model = ScriptedChatModel(
        replies=[
            ai("", call("read_file", call_id="bad", offset=0)),
            ai("", call("read_file", call_id="good", path="a.txt")),
            ai("Fixed it."),
        ]
    )

    messages = run(graph, make_context(tmp_path, model), ask("read a.txt"))

    first, second = tool_messages(messages)
    assert "invalid arguments" in str(first.content) and "path" in str(first.content)
    assert "1: A" in str(second.content)


def test_malformed_json_call_still_gets_a_tool_message(graph: Any, tmp_path: Path) -> None:
    broken = AIMessage(
        content="",
        invalid_tool_calls=[
            {
                "name": "bash",
                "args": "{oops",
                "id": "m1",
                "error": "bad json",
                "type": "invalid_tool_call",
            }
        ],
    )
    model = ScriptedChatModel(replies=[broken, ai("Sorry, retrying differently.")])

    messages = run(graph, make_context(tmp_path, model), ask("run ls"))

    [reply] = tool_messages(messages)
    assert reply.tool_call_id == "m1"
    assert "not valid JSON" in str(reply.content)


def test_unknown_tool_lists_available_tools(graph: Any, tmp_path: Path) -> None:
    model = ScriptedChatModel(replies=[ai("", call("cat", path="x")), ai("ok")])

    messages = run(graph, make_context(tmp_path, model), ask("cat x"))

    assert "Available tools" in str(tool_messages(messages)[0].content)


def test_step_budget_forces_a_final_answer(graph: Any, tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("A\n")
    model = ScriptedChatModel(
        replies=[ai("", call("read_file", path="a.txt")), ai("Out of steps; here is a summary.")]
    )

    run(graph, make_context(tmp_path, model, max_steps=1), ask("go"))

    assert model.bind_kwargs[-1] == {"tool_choice": "none"}
    assert model.requests[-1][-1].content == FINAL_STEP_NOTE


def test_resume_does_not_rerun_side_effects(graph: Any, tmp_path: Path) -> None:
    CounterTool.runs.clear()
    registry = ToolRegistry([ReadFileTool(), CounterTool()])
    model = ScriptedChatModel(
        replies=[
            ai(
                "",
                call("counter", call_id="a", label="one"),
                call("counter", call_id="b", label="two"),
            ),
            ai("Counted twice."),
        ]
    )
    ctx = make_context(tmp_path, model, registry=registry)

    run(graph, ctx, ask("count"))
    [pending] = graph.get_state(CONFIG).interrupts
    assert len(pending.value["requests"]) == 2  # both asked in one prompt

    yes = {"approved": True, "feedback": None}
    run(graph, ctx, Command(resume={"a": yes, "b": yes}))

    assert CounterTool.runs == ["one", "two"]  # each ran exactly once


def test_default_registry_is_used_by_context(tmp_path: Path) -> None:
    ctx = make_context(tmp_path, ScriptedChatModel(replies=[]))

    assert set(ctx.tools.names()) >= set(default_registry().names()) - {"bash", "powershell"}
