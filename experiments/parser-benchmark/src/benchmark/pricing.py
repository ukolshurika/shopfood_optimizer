from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Usage:
    input_tokens: int | None = None
    cached_input_tokens: int | None = None
    output_tokens: int | None = None
    reasoning_tokens: int | None = None
    total_tokens: int | None = None


def calculate_cost_usd(usage: Usage, pricing: dict) -> float | None:
    input_price = pricing.get("input_per_1m")
    cached_input_price = pricing.get("cached_input_per_1m")
    output_price = pricing.get("output_per_1m")

    if input_price is None or output_price is None:
        return None

    input_tokens = usage.input_tokens or 0
    cached_tokens = usage.cached_input_tokens or 0
    output_tokens = usage.output_tokens or 0

    billable_uncached_input = max(input_tokens - cached_tokens, 0)
    input_cost = billable_uncached_input * float(input_price) / 1_000_000
    cached_cost = 0.0
    if cached_tokens:
        if cached_input_price is None:
            return None
        cached_cost = cached_tokens * float(cached_input_price) / 1_000_000
    output_cost = output_tokens * float(output_price) / 1_000_000
    return input_cost + cached_cost + output_cost
