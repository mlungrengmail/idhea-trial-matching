"""Lightweight LLM client for trial rule extraction.

Supports two providers:
  - OpenAI-compatible (default): any endpoint implementing /chat/completions
  - Anthropic: native Messages API at https://api.anthropic.com

Provider is selected via TRIAL_MATCHING_LLM_PROVIDER env var ('openai' or 'anthropic').
API keys are read from environment variables only — never hardcoded.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field

try:
    import requests
except ImportError as exc:  # pragma: no cover - dependency guard
    raise SystemExit(f"Missing dependency: {exc}. Run: uv sync")

VALID_PROVIDERS = {"openai", "anthropic"}


@dataclass
class LLMConfig:
    api_key: str
    model: str
    provider: str = "openai"
    base_url: str = "https://api.openai.com/v1"
    timeout_seconds: int = 90
    max_tokens: int = 4096


def load_llm_config_from_env() -> LLMConfig | None:
    """Load LLM configuration from environment variables.

    Required:
      TRIAL_MATCHING_LLM_API_KEY - API key for the selected provider
      TRIAL_MATCHING_LLM_MODEL - model name (e.g., 'gpt-4.1-mini', 'claude-sonnet-4-20250514')

    Optional:
      TRIAL_MATCHING_LLM_PROVIDER - 'openai' (default) or 'anthropic'
      TRIAL_MATCHING_LLM_BASE_URL - base URL override (OpenAI provider only)
      TRIAL_MATCHING_LLM_TIMEOUT_SECONDS - request timeout (default: 90)
      TRIAL_MATCHING_LLM_MAX_TOKENS - max output tokens (default: 4096)
    """
    api_key = os.getenv("TRIAL_MATCHING_LLM_API_KEY", "").strip()
    model = os.getenv("TRIAL_MATCHING_LLM_MODEL", "").strip()
    if not api_key or not model:
        return None
    provider = os.getenv("TRIAL_MATCHING_LLM_PROVIDER", "openai").strip().lower()
    if provider not in VALID_PROVIDERS:
        raise ValueError(f"Unsupported provider: {provider}. Use: {', '.join(sorted(VALID_PROVIDERS))}")

    if provider == "anthropic":
        base_url = "https://api.anthropic.com"
    else:
        base_url = os.getenv("TRIAL_MATCHING_LLM_BASE_URL", "https://api.openai.com/v1").strip()

    timeout_seconds = int(os.getenv("TRIAL_MATCHING_LLM_TIMEOUT_SECONDS", "90"))
    max_tokens = int(os.getenv("TRIAL_MATCHING_LLM_MAX_TOKENS", "4096"))
    return LLMConfig(
        api_key=api_key,
        model=model,
        provider=provider,
        base_url=base_url.rstrip("/"),
        timeout_seconds=timeout_seconds,
        max_tokens=max_tokens,
    )


def extract_json_payload(text: str) -> dict:
    value = text.strip()
    if value.startswith("```"):
        lines = value.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        value = "\n".join(lines).strip()
    return json.loads(value)


class OpenAICompatibleLLMClient:
    def __init__(self, config: LLMConfig):
        self.config = config

    @property
    def model_name(self) -> str:
        return self.config.model

    def extract_rules(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> dict:
        response = requests.post(
            f"{self.config.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": self.config.model,
                "temperature": 0,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            },
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        content = payload["choices"][0]["message"]["content"]
        return extract_json_payload(content)


class AnthropicLLMClient:
    """Native Anthropic Messages API client."""

    ANTHROPIC_API_VERSION = "2023-06-01"

    def __init__(self, config: LLMConfig):
        self.config = config

    @property
    def model_name(self) -> str:
        return self.config.model

    def extract_rules(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
    ) -> dict:
        response = requests.post(
            f"{self.config.base_url}/v1/messages",
            headers={
                "x-api-key": self.config.api_key,
                "anthropic-version": self.ANTHROPIC_API_VERSION,
                "Content-Type": "application/json",
            },
            json={
                "model": self.config.model,
                "max_tokens": self.config.max_tokens,
                "temperature": 0,
                "system": system_prompt,
                "messages": [
                    {"role": "user", "content": user_prompt},
                ],
            },
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        # Anthropic returns content as a list of blocks
        content_blocks = payload.get("content", [])
        text_parts = [
            block["text"] for block in content_blocks if block.get("type") == "text"
        ]
        content = "\n".join(text_parts)
        return extract_json_payload(content)


def create_llm_client(config: LLMConfig) -> OpenAICompatibleLLMClient | AnthropicLLMClient:
    """Factory: create the appropriate client for the configured provider."""
    if config.provider == "anthropic":
        return AnthropicLLMClient(config)
    return OpenAICompatibleLLMClient(config)
