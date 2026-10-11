import pytest
from langchain_deepseek import ChatDeepSeek

from buildra.config.schema import LLMSettings, ProviderSettings
from buildra.llm import LLMConfigError, ModelRef, available_providers, create_chat_model
from buildra.llm.providers.deepseek import thinking_payload

KEY_ENV = {"DEEPSEEK_API_KEY": "sk-test"}


def test_model_ref_parses_provider_and_model() -> None:
    ref = ModelRef.parse("DeepSeek/deepseek-flash")

    assert ref == ModelRef(provider="deepseek", model="deepseek-flash")
    assert str(ref) == "deepseek/deepseek-flash"


def test_model_ref_keeps_slashes_in_model_part() -> None:
    assert ModelRef.parse("openrouter/meta/llama").model == "meta/llama"


@pytest.mark.parametrize("bad", ["deepseek-flash", "/model", "deepseek/", ""])
def test_model_ref_rejects_malformed_ids(bad: str) -> None:
    with pytest.raises(LLMConfigError, match="provider/model"):
        ModelRef.parse(bad)


def test_deepseek_is_registered() -> None:
    assert "deepseek" in available_providers()


def test_unknown_provider_lists_available_ones() -> None:
    with pytest.raises(LLMConfigError, match="Available: deepseek"):
        create_chat_model(LLMSettings(model="nope/model"), env=KEY_ENV)


def test_missing_api_key_names_the_variable() -> None:
    with pytest.raises(LLMConfigError, match="DEEPSEEK_API_KEY"):
        create_chat_model(LLMSettings(), env={})


def test_deepseek_model_is_configured_from_settings() -> None:
    settings = LLMSettings(model="deepseek/deepseek-v4-pro", max_retries=2, request_timeout_s=30)

    chat = create_chat_model(settings, env=KEY_ENV)

    assert isinstance(chat, ChatDeepSeek)
    assert chat.model_name == "deepseek-v4-pro"
    assert chat.max_retries == 2
    assert chat.stream_usage is True
    assert chat.extra_body == {"thinking": {"type": "disabled"}}


def test_model_argument_overrides_settings() -> None:
    chat = create_chat_model(LLMSettings(), model="deepseek/deepseek-v4-pro", env=KEY_ENV)

    assert isinstance(chat, ChatDeepSeek)
    assert chat.model_name == "deepseek-v4-pro"


def test_provider_overrides_key_variable_and_base_url() -> None:
    settings = LLMSettings(
        providers={"deepseek": ProviderSettings(api_key_env="MY_KEY", base_url="http://proxy/v1")}
    )

    chat = create_chat_model(settings, env={"MY_KEY": "sk-other"})

    assert isinstance(chat, ChatDeepSeek)
    assert chat.api_base == "http://proxy/v1"
    assert chat.api_key is not None
    assert chat.api_key.get_secret_value() == "sk-other"


def test_thinking_payload_maps_reasoning_levels() -> None:
    assert thinking_payload("off") == {"type": "disabled"}
    assert thinking_payload("high") == {"type": "enabled", "reasoning_effort": "high"}
