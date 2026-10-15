from pathlib import Path
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver

from buildra.agent import build_graph
from buildra.agent.approval import ApprovalAnswers, ApprovalPrompt
from buildra.cli.approval import parse_answer
from buildra.cli.turn import CANCELLED, TurnRunner
from fakes import ScriptedChatModel, ai, call, make_context


class RecordingView:
    def __init__(self) -> None:
        self.events: list[tuple[str, Any]] = []

    def text(self, chunk: str) -> None:
        self.events.append(("text", chunk))

    def reasoning(self, chunk: str) -> None:
        self.events.append(("reasoning", chunk))

    def tool_start(self, tool: str, summary: str) -> None:
        self.events.append(("tool_start", (tool, summary)))

    def tool_result(self, message: ToolMessage) -> None:
        self.events.append(("tool_result", message.status))

    def pause(self) -> None:
        self.events.append(("pause", None))

    def end_of_turn(self) -> None:
        self.events.append(("end", None))


class ScriptedApprover:
    def __init__(self, *answers: str) -> None:
        self.answers = list(answers)
        self.prompts: list[ApprovalPrompt] = []

    def decide(self, prompt: ApprovalPrompt) -> ApprovalAnswers:
        self.prompts.append(prompt)
        return {r["call_id"]: parse_answer(self.answers.pop(0)) for r in prompt["requests"]}


def make_runner(
    tmp_path: Path, model: ScriptedChatModel, approver: ScriptedApprover
) -> tuple[TurnRunner, RecordingView]:
    view = RecordingView()
    runner = TurnRunner(
        graph=build_graph(InMemorySaver()),
        context=make_context(tmp_path, model),
        view=view,
        approver=approver,
        thread_id="t",
    )
    return runner, view


def test_turn_streams_text_and_tool_events(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("A\n")
    model = ScriptedChatModel(
        replies=[ai("Looking.", call("read_file", path="a.txt")), ai("Done.")]
    )
    runner, view = make_runner(tmp_path, model, ScriptedApprover())

    runner.run("read a.txt")

    kinds = [kind for kind, _ in view.events]
    assert kinds == ["text", "tool_start", "tool_result", "text", "end"]
    assert ("tool_start", ("read_file", "a.txt")) in view.events


def test_parallel_calls_show_each_result_right_after_its_start(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_text("A\n")
    (tmp_path / "b.txt").write_text("B\n")
    model = ScriptedChatModel(
        replies=[
            ai("", call("read_file", "1", path="a.txt"), call("read_file", "2", path="b.txt")),
            ai("ok"),
        ]
    )
    runner, view = make_runner(tmp_path, model, ScriptedApprover())

    runner.run("read both")

    tool_events = [kind for kind, _ in view.events if kind.startswith("tool")]
    assert tool_events == ["tool_start", "tool_result", "tool_start", "tool_result"]


def test_turn_resumes_after_approval(tmp_path: Path) -> None:
    model = ScriptedChatModel(
        replies=[ai("", call("write_file", path="b.txt", content="B")), ai("Written.")]
    )
    approver = ScriptedApprover("y")
    runner, view = make_runner(tmp_path, model, approver)

    runner.run("write b.txt")

    assert approver.prompts[0]["requests"][0]["tool"] == "write_file"
    assert ("pause", None) in view.events  # the line was finished before asking
    assert (tmp_path / "b.txt").read_text() == "B"
    assert ("text", "Written.") in view.events


def test_cancel_closes_dangling_tool_calls(tmp_path: Path) -> None:
    model = ScriptedChatModel(
        replies=[ai("", call("write_file", path="c.txt", content="C")), ai("Hi again.")]
    )
    runner, _ = make_runner(tmp_path, model, ScriptedApprover())
    # Simulate Ctrl+C while waiting for approval: stream until the interrupt, then stop.
    runner._stream({"messages": [HumanMessage("write c")]})

    runner.cancel()
    runner.run("never mind, just say hi")

    messages = runner.graph.get_state(runner.config).values["messages"]
    closing = [m for m in messages if isinstance(m, ToolMessage)]
    assert [m.content for m in closing] == [CANCELLED]
    assert isinstance(messages[-1], AIMessage) and messages[-1].content == "Hi again."
    assert not (tmp_path / "c.txt").exists()


def test_parse_answer() -> None:
    assert parse_answer(" Y ") == {"approved": True, "feedback": None}
    assert parse_answer("") == {"approved": False, "feedback": None}
    assert parse_answer("no") == {"approved": False, "feedback": None}
    assert parse_answer("use b.txt") == {"approved": False, "feedback": "use b.txt"}
    assert parse_answer("\ufeffy") == {"approved": True, "feedback": None}  # BOM from a pipe
