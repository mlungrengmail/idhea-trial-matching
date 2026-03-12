"""Tests for llm_client module."""

import os
from unittest.mock import patch

from scripts.llm_client import (
    AnthropicLLMClient,
    LLMConfig,
    OpenAICompatibleLLMClient,
    create_llm_client,
    extract_json_payload,
    load_llm_config_from_env,
)


class TestExtractJsonPayload:
    def test_plain_json(self):
        result = extract_json_payload('{"rules": []}')
        assert result == {"rules": []}

    def test_fenced_json(self):
        text = '```json\n{"rules": []}\n```'
        result = extract_json_payload(text)
        assert result == {"rules": []}

    def test_whitespace(self):
        result = extract_json_payload('  \n{"key": "value"}\n  ')
        assert result == {"key": "value"}


class TestLoadLLMConfigFromEnv:
    def test_returns_none_without_key(self):
        with patch.dict(os.environ, {}, clear=True):
            assert load_llm_config_from_env() is None

    def test_openai_default(self):
        env = {
            "TRIAL_MATCHING_LLM_API_KEY": "test-key",
            "TRIAL_MATCHING_LLM_MODEL": "gpt-4.1-mini",
        }
        with patch.dict(os.environ, env, clear=True):
            config = load_llm_config_from_env()
            assert config is not None
            assert config.provider == "openai"
            assert config.base_url == "https://api.openai.com/v1"

    def test_anthropic_provider(self):
        env = {
            "TRIAL_MATCHING_LLM_API_KEY": "test-key",
            "TRIAL_MATCHING_LLM_MODEL": "claude-sonnet-4-20250514",
            "TRIAL_MATCHING_LLM_PROVIDER": "anthropic",
        }
        with patch.dict(os.environ, env, clear=True):
            config = load_llm_config_from_env()
            assert config is not None
            assert config.provider == "anthropic"
            assert config.base_url == "https://api.anthropic.com"

    def test_invalid_provider_raises(self):
        env = {
            "TRIAL_MATCHING_LLM_API_KEY": "test-key",
            "TRIAL_MATCHING_LLM_MODEL": "model",
            "TRIAL_MATCHING_LLM_PROVIDER": "invalid",
        }
        with patch.dict(os.environ, env, clear=True):
            try:
                load_llm_config_from_env()
                assert False, "Should have raised ValueError"
            except ValueError as exc:
                assert "invalid" in str(exc)


class TestCreateLLMClient:
    def test_openai_client(self):
        config = LLMConfig(api_key="k", model="m", provider="openai")
        client = create_llm_client(config)
        assert isinstance(client, OpenAICompatibleLLMClient)

    def test_anthropic_client(self):
        config = LLMConfig(api_key="k", model="m", provider="anthropic")
        client = create_llm_client(config)
        assert isinstance(client, AnthropicLLMClient)

    def test_model_name_property(self):
        config = LLMConfig(api_key="k", model="test-model", provider="anthropic")
        client = create_llm_client(config)
        assert client.model_name == "test-model"
