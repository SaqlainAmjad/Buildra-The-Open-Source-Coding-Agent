from pathlib import Path

import pytest
from typer.testing import CliRunner

from buildra import __version__
from buildra.cli.app import app

runner = CliRunner()


def test_version() -> None:
    result = runner.invoke(app, ["--version"])

    assert result.exit_code == 0
    assert __version__ in result.output


def test_missing_api_key_is_a_friendly_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)

    result = runner.invoke(app, ["--workdir", str(tmp_path), "hello"])

    assert result.exit_code == 1
    assert "DEEPSEEK_API_KEY is not set" in result.output


def test_bad_model_id_is_a_friendly_error(tmp_path: Path) -> None:
    result = runner.invoke(app, ["--workdir", str(tmp_path), "--model", "flash", "hello"])

    assert result.exit_code == 1
    assert "provider/model" in result.output
