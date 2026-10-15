from pathlib import Path

import pytest

from buildra.config.schema import ToolSettings
from buildra.permissions.sandbox import Workspace
from buildra.tools import ToolContext


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    return root


@pytest.fixture
def ctx(workspace: Path) -> ToolContext:
    return ToolContext(workspace=Workspace(workspace), settings=ToolSettings())
