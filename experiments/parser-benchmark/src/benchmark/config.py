from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ProviderPlan:
    provider: str
    model: str | None
    prompt: str
    mode: str
    response_mode: str
    pricing_complete: bool
    api_key_env: str
    base_url_env: str
    project_env: str | None
    auth_scheme: str
    transport: str


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def build_plan(config: dict[str, Any], *, mode: str) -> list[ProviderPlan]:
    plan: list[ProviderPlan] = []
    for provider_name, provider_config in config["providers"].items():
        if not provider_config.get("enabled", False):
            continue
        model = os.environ.get(provider_config["model_env"])
        response_mode = provider_config["response_modes"][mode]
        pricing = provider_config.get("pricing", {})
        pricing_complete = pricing.get("input_per_1m") is not None and pricing.get("output_per_1m") is not None
        for prompt in provider_config["prompt_variants"]:
            plan.append(
                ProviderPlan(
                    provider=provider_name,
                    model=model,
                    prompt=prompt,
                    mode=mode,
                    response_mode=response_mode,
                    pricing_complete=pricing_complete,
                    api_key_env=provider_config.get("api_key_env", f"{provider_name.upper()}_API_KEY"),
                    base_url_env=provider_config.get("base_url_env", f"{provider_name.upper()}_BASE_URL"),
                    project_env=provider_config.get("project_env"),
                    auth_scheme=provider_config.get("auth_scheme", "bearer"),
                    transport=provider_config.get("transport", "chat_completions"),
                )
            )
    return plan


def quality_gates(config: dict[str, Any]) -> dict[str, float]:
    return config["benchmark"]["quality_gates"]
