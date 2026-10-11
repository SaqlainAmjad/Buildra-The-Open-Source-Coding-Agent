"""Build :class:`Settings` from config files and the environment.

Sources, lowest to highest precedence (the same layering opencode uses in
``config/config.ts``):

1. built-in defaults (``schema.py``)
2. the global file: ``<user config dir>/buildra/config.toml``
3. the project file: ``<workdir>/.buildra/config.toml``
4. environment variables (``BUILDRA_MODEL``, ``BUILDRA_REASONING``)

Files are deep-merged as plain dicts first and validated once at the end, so
a project file can override a single nested key without repeating the rest.
"""

import os
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import platformdirs
from pydantic import ValidationError

from buildra.config.schema import Settings

PROJECT_CONFIG = Path(".buildra") / "config.toml"

_ENV_OVERRIDES: dict[str, tuple[str, ...]] = {
    "BUILDRA_MODEL": ("llm", "model"),
    "BUILDRA_REASONING": ("llm", "reasoning"),
}


class ConfigError(Exception):
    """A config file could not be read or does not match the schema."""


def global_config_path() -> Path:
    """Return the per-user config file location for this platform."""
    return Path(platformdirs.user_config_dir("buildra", appauthor=False)) / "config.toml"


def load_settings(
    workdir: Path,
    *,
    global_path: Path | None = None,
    env: Mapping[str, str] | None = None,
) -> Settings:
    """Load, merge and validate settings for a project directory.

    Args:
        workdir: The project directory the agent works in.
        global_path: Override for the global config file (used by tests).
        env: Environment to read overrides from; defaults to ``os.environ``.

    Raises:
        ConfigError: If a file is not valid TOML or the merged result is invalid.
    """
    sources = [global_path or global_config_path(), workdir / PROJECT_CONFIG]
    merged: dict[str, Any] = {}
    for path in sources:
        merged = _deep_merge(merged, _read_toml(path))
    merged = _deep_merge(merged, _env_overrides(os.environ if env is None else env))
    try:
        return Settings.model_validate(merged)
    except ValidationError as error:
        files = ", ".join(str(p) for p in sources if p.is_file()) or "defaults"
        raise ConfigError(f"Invalid configuration (from {files}):\n{error}") from error


def _read_toml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        with path.open("rb") as file:
            return tomllib.load(file)
    except tomllib.TOMLDecodeError as error:
        raise ConfigError(f"{path}: {error}") from error


def _env_overrides(env: Mapping[str, str]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name, (section, key) in _ENV_OVERRIDES.items():
        if value := env.get(name):
            result.setdefault(section, {})[key] = value
    return result


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Return ``base`` updated by ``override``, merging nested dicts key by key."""
    result = dict(base)
    for key, value in override.items():
        current = result.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            result[key] = _deep_merge(current, value)
        else:
            result[key] = value
    return result
