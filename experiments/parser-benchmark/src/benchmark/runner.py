from __future__ import annotations

import asyncio
import json
import os
from dataclasses import asdict
from pathlib import Path
from typing import Any

from benchmark.config import ProviderPlan
from benchmark.dataset import DatasetCase
from benchmark.evaluator import evaluate_case, evaluation_to_dict
from benchmark.models import shopping_list_schema
from benchmark.pricing import calculate_cost_usd
from benchmark.providers.base import ProviderResult
from benchmark.providers.gigachat_provider import GigaChatProvider
from benchmark.providers.http import ChatCompletionsProvider, OpenAIResponsesProvider


def build_provider(plan: ProviderPlan, config: dict[str, Any]):
    provider_config = config["providers"][plan.provider]
    request_params = provider_config.get("request_params") or {}
    user_prefix = provider_config.get("user_prefix") or ""
    timeout = int(config["benchmark"]["timeout_seconds"])
    max_output_tokens = int(config["benchmark"]["max_output_tokens"])
    model = plan.model
    api_key = os.environ.get(plan.api_key_env)
    base_url = os.environ.get(plan.base_url_env)
    project_id = os.environ.get(plan.project_env) if plan.project_env else None
    if not api_key or not model or not base_url:
        return None
    if plan.provider == "gigachat_freemium":
        return GigaChatProvider(
            credentials=api_key,
            scope=os.environ.get("GIGACHAT_SCOPE", "GIGACHAT_API_PERS"),
            model=model,
            base_url=base_url,
            oauth_url=os.environ.get("GIGACHAT_OAUTH_URL", "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"),
            timeout_seconds=timeout,
            max_output_tokens=max_output_tokens,
            verify_ssl=os.environ.get("GIGACHAT_VERIFY_SSL", "true").lower() != "false",
        )
    if provider_config.get("transport") == "responses":
        return OpenAIResponsesProvider(
            provider=plan.provider,
            api_key=api_key,
            model=model,
            base_url=base_url,
            timeout_seconds=timeout,
            max_output_tokens=max_output_tokens,
            auth_scheme=plan.auth_scheme,
            project_id=project_id,
            request_params=request_params,
            user_prefix=user_prefix,
        )
    return ChatCompletionsProvider(
        provider=plan.provider,
        api_key=api_key,
        model=model,
        base_url=base_url,
        timeout_seconds=timeout,
        max_output_tokens=max_output_tokens,
        auth_scheme=plan.auth_scheme,
        project_id=project_id,
        request_params=request_params,
        user_prefix=user_prefix,
    )


async def run_live(
    *,
    cases: list[DatasetCase],
    plan: list[ProviderPlan],
    config: dict[str, Any],
    prompts_dir: Path,
    out_dir: Path,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    out_dir.mkdir(parents=True, exist_ok=True)
    selected_cases = cases[:limit] if limit else cases
    schema = shopping_list_schema()
    evaluated_rows: list[dict[str, Any]] = []

    with (out_dir / "raw_attempts.jsonl").open("w", encoding="utf-8") as raw_file:
        for plan_item in plan:
            provider = build_provider(plan_item, config)
            if provider is None:
                continue
            prompt = (prompts_dir / f"{plan_item.prompt}.md").read_text(encoding="utf-8")
            for case in selected_cases:
                result = await _parse_with_retries(
                    provider=provider,
                    plan_item=plan_item,
                    case=case,
                    prompt=prompt,
                    schema=schema,
                    config=config,
                )
                raw_file.write(json.dumps(_provider_result_row(result, case.id, plan_item), ensure_ascii=False) + "\n")
                evaluation = evaluate_case(
                    gold=case.gold,
                    prediction=result.parsed_json,
                    evaluator_metadata=case.evaluator_metadata,
                )
                cost_usd = calculate_cost_usd(
                    result.usage,
                    config["providers"][plan_item.provider].get("pricing", {}),
                )
                evaluated_rows.append(
                    {
                        "id": case.id,
                        "category": case.category,
                        "provider": plan_item.provider,
                        "model": plan_item.model,
                        "prompt": plan_item.prompt,
                        "mode": plan_item.mode,
                        "response_mode": plan_item.response_mode,
                        "latency_ms": result.latency_ms,
                        "cost_usd": cost_usd,
                        "input_tokens": result.usage.input_tokens,
                        "output_tokens": result.usage.output_tokens,
                        "total_tokens": result.usage.total_tokens,
                        "error_type": result.error_type,
                        **evaluation_to_dict(evaluation),
                    }
                )
    return evaluated_rows


async def _parse_with_retries(
    *,
    provider,
    plan_item: ProviderPlan,
    case: DatasetCase,
    prompt: str,
    schema: dict,
    config: dict[str, Any],
) -> ProviderResult:
    max_attempts = 1 + int(os.environ.get("BENCHMARK_NETWORK_RETRIES", 0)) + int(os.environ.get("BENCHMARK_SCHEMA_RETRIES", 0))
    last_result: ProviderResult | None = None
    for attempt in range(1, max_attempts + 1):
        result = await provider.parse(
            system_prompt=prompt,
            user_text=case.input,
            schema=schema,
            response_mode=plan_item.response_mode,
        )
        result.attempt = attempt
        last_result = result
        if result.error_type is None:
            return result
        if result.error_type == "HTTP_4XX":
            return result
        await asyncio.sleep(min(attempt, 3))
    assert last_result is not None
    return last_result


def _provider_result_row(result: ProviderResult, case_id: str, plan_item: ProviderPlan) -> dict[str, Any]:
    row = asdict(result)
    row["case_id"] = case_id
    row["prompt"] = plan_item.prompt
    row["mode"] = plan_item.mode
    row["response_mode"] = plan_item.response_mode
    return row
