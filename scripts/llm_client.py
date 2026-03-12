"""Lightweight OpenAI-compatible LLM client for trial rule extraction."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

try:
    import requests
except ImportError as exc:  # pragma: no cover - dependency guard
    raise SystemExit(f"Missing dependency: {exc}. Run: uv sync")


@dataclass
class LLMConfig:
    api_key: str
    model: str
    base_url: str = "https://api.openai.com/v1"
    timeout_seconds: int = 90


def load_llm_config_from_env() -> LLMConfig | None:
    api_key = os.getenv("TRIAL_MATCHING_LLM_API_KEY", "").strip()
    model = os.getenv("TRIAL_MATCHING_LLM_MODEL", "").strip()
    if not api_key or not model:
        return None
    base_url = os.getenv("TRIAL_MATCHING_LLM_BASE_URL", "https://api.openai.com/v1").strip()
    timeout_seconds = int(os.getenv("TRIAL_MATCHING_LLM_TIMEOUT_SECONDS", "90"))
    return LLMConfig(
        api_key=api_key,
        model=model,
        base_url=base_url.rstrip("/"),
        timeout_seconds=timeout_seconds,
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
