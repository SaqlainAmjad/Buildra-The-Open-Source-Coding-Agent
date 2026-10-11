"""Errors raised while turning settings into a chat model."""


class LLMConfigError(Exception):
    """The model settings cannot produce a working chat model (bad id, missing key...)."""
