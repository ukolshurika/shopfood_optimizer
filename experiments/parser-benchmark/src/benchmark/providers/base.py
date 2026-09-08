from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from benchmark.pricing import Usage


@dataclass
class ProviderResult:
    provider: str
    model: str
    raw_text: str | None
    parsed_json: dict[str, Any] | None
    usage: Usage
    latency_ms: float
    http_status: int | None
    response_id: str | None
    error_type: str | None
    error_message: str | None
    attempt: int


class Provider(Protocol):
    async def parse(
        self,
        *,
        system_prompt: str,
        user_text: str,
        schema: dict,
        response_mode: str,
    ) -> ProviderResult:
        ...
