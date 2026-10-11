"""Live checks against the real DeepSeek API.

Run with ``uv run pytest -m live -s`` after putting DEEPSEEK_API_KEY in .env.
These double as the Day 1 spike: they confirm the model names, tool calling,
streaming with usage, and how thinking mode behaves in a tool loop.
"""

import json
import os
import urllib.request
from pathlib import Path

import pytest
from dotenv import load_dotenv
from langchain_core.messages import AIMessageChunk, BaseMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool

from buildra.config.schema import LLMSettings, Reasoning
from buildra.llm import create_chat_model

load_dotenv(Path(__file__).parents[2] / ".env")

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(not os.environ.get("DEEPSEEK_API_KEY"), reason="DEEPSEEK_API_KEY not set"),
]


@tool
def get_weather(city: str) -> str:
    """Return the current weather for a city."""
    return f"It is sunny and 21C in {city}."


def test_list_models() -> None:
    request = urllib.request.Request(
        "https://api.deepseek.com/models",
        headers={"Authorization": f"Bearer {os.environ['DEEPSEEK_API_KEY']}"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        ids = [m["id"] for m in json.load(response)["data"]]
    print("models:", ids)
    assert "deepseek-flash" in ids


def test_streaming_reports_usage() -> None:
    chat = create_chat_model(LLMSettings())

    chunks = list(chat.stream([HumanMessage("Reply with exactly: pong")]))

    merged = sum(chunks[1:], chunks[0])
    assert isinstance(merged, AIMessageChunk)
    print("text:", merged.content, "| usage:", merged.usage_metadata)
    assert "pong" in str(merged.content).lower()
    assert merged.usage_metadata is not None


@pytest.mark.parametrize("reasoning", ["off", "high"])
def test_tool_round_trip(reasoning: Reasoning) -> None:
    chat = create_chat_model(LLMSettings(reasoning=reasoning)).bind_tools([get_weather])
    history: list[BaseMessage] = [HumanMessage("What's the weather in Lahore? Use the tool.")]

    first = chat.invoke(history)
    print(f"[{reasoning}] tool_calls:", first.tool_calls)
    print(f"[{reasoning}] reasoning:", str(first.additional_kwargs.get("reasoning_content"))[:200])
    assert first.tool_calls, "model should call the tool"

    call = first.tool_calls[0]
    history += [first, ToolMessage(get_weather.invoke(call["args"]), tool_call_id=call["id"])]
    second = chat.invoke(history)
    print(f"[{reasoning}] final:", second.content)
    assert "21" in str(second.content)
