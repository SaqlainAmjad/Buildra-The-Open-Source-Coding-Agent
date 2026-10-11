from pathlib import Path

import pytest

from buildra.config import ConfigError, load_settings
from buildra.config.loader import PROJECT_CONFIG


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def no_global(tmp_path: Path) -> Path:
    return tmp_path / "missing-global.toml"


def test_defaults_when_no_files(tmp_path: Path, no_global: Path) -> None:
    settings = load_settings(tmp_path, global_path=no_global, env={})

    assert settings.llm.model == "deepseek/deepseek-flash"
    assert settings.llm.reasoning == "off"
    assert settings.agent.max_steps == 50


def test_project_file_overrides_global_key_by_key(tmp_path: Path) -> None:
    global_file = write(
        tmp_path / "global.toml",
        '[llm]\nmodel = "deepseek/deepseek-v4-pro"\nmax_retries = 5\n',
    )
    write(tmp_path / PROJECT_CONFIG, "[llm]\nmax_retries = 1\n")

    settings = load_settings(tmp_path, global_path=global_file, env={})

    assert settings.llm.model == "deepseek/deepseek-v4-pro"  # kept from global
    assert settings.llm.max_retries == 1  # overridden by project


def test_nested_provider_override_merges(tmp_path: Path) -> None:
    global_file = write(
        tmp_path / "global.toml",
        '[llm.providers.deepseek]\napi_key_env = "MY_KEY"\n',
    )
    write(tmp_path / PROJECT_CONFIG, '[llm.providers.deepseek]\nbase_url = "http://proxy"\n')

    settings = load_settings(tmp_path, global_path=global_file, env={})

    provider = settings.llm.providers["deepseek"]
    assert provider.api_key_env == "MY_KEY"
    assert provider.base_url == "http://proxy"


def test_environment_beats_files(tmp_path: Path, no_global: Path) -> None:
    write(tmp_path / PROJECT_CONFIG, '[llm]\nmodel = "deepseek/deepseek-flash"\n')

    settings = load_settings(
        tmp_path,
        global_path=no_global,
        env={"BUILDRA_MODEL": "deepseek/deepseek-v4-pro", "BUILDRA_REASONING": "high"},
    )

    assert settings.llm.model == "deepseek/deepseek-v4-pro"
    assert settings.llm.reasoning == "high"


def test_unknown_key_is_rejected(tmp_path: Path, no_global: Path) -> None:
    write(tmp_path / PROJECT_CONFIG, "[llm]\nmodle = 'typo'\n")

    with pytest.raises(ConfigError, match="modle"):
        load_settings(tmp_path, global_path=no_global, env={})


def test_invalid_toml_names_the_file(tmp_path: Path, no_global: Path) -> None:
    bad = write(tmp_path / PROJECT_CONFIG, "[llm\n")

    with pytest.raises(ConfigError, match=str(bad).replace("\\", r"\\")):
        load_settings(tmp_path, global_path=no_global, env={})
