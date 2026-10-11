"""Configuration: a validated settings schema and the loader that builds it."""

from buildra.config.loader import ConfigError, load_settings
from buildra.config.schema import Settings

__all__ = ["ConfigError", "Settings", "load_settings"]
