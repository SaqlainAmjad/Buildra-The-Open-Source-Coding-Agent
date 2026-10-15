import sys

import pytest

from buildra.tools import InvalidToolCall, ToolRegistry, default_registry
from buildra.tools.read_file import ReadFileTool
from buildra.tools.registry import malformed_arguments_message


def test_prepare_validates_arguments() -> None:
    registry = ToolRegistry([ReadFileTool()])

    call = registry.prepare("read_file", {"path": "a.py", "offset": 3})

    assert call.args.offset == 3
    assert call.summary() == "a.py (from line 3)"


def test_unknown_tool_lists_available() -> None:
    with pytest.raises(InvalidToolCall, match="Available tools: read_file"):
        ToolRegistry([ReadFileTool()]).prepare("cat", {})


def test_invalid_arguments_are_explained_for_the_model() -> None:
    with pytest.raises(InvalidToolCall) as info:
        ToolRegistry([ReadFileTool()]).prepare("read_file", {"offset": 0})

    message = str(info.value)
    assert "path: Field required" in message
    assert "offset" in message
    assert "Rewrite the call" in message


def test_duplicate_names_are_rejected() -> None:
    with pytest.raises(ValueError, match="Duplicate"):
        ToolRegistry([ReadFileTool(), ReadFileTool()])


def test_schema_is_openai_function_format() -> None:
    schema = ReadFileTool().schema()

    assert schema["function"]["name"] == "read_file"
    assert schema["function"]["parameters"]["required"] == ["path"]
    assert "title" not in schema["function"]["parameters"]


def test_default_registry_has_core_tools() -> None:
    names = default_registry().names()

    assert {"read_file", "write_file", "edit_file", "list_dir", "glob", "grep"} <= set(names)
    assert ("powershell" in names) == (sys.platform == "win32")


def test_malformed_json_message() -> None:
    message = malformed_arguments_message("bash", "Expecting value")

    assert "not valid JSON: Expecting value" in message
