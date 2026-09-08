from __future__ import annotations

import asyncio
import json
import time
import urllib.error
import urllib.request
from typing import Any

from pydantic import ValidationError

from benchmark.json_utils import parse_json_text
from benchmark.models import ShoppingList
from benchmark.pricing import Usage
from benchmark.providers.base import ProviderResult


def post_json(
    *,
    url: str,
    api_key: str,
    payload: dict[str, Any],
    timeout_seconds: int,
    auth_scheme: str = "bearer",
    project_id: str | None = None,
) -> tuple[int, dict[str, Any]]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    authorization = f"Api-Key {api_key}" if auth_scheme == "yandex_api_key" else f"Bearer {api_key}"
    headers = {
        "Authorization": authorization,
        "Content-Type": "application/json",
    }
    if project_id:
        headers["OpenAI-Project"] = project_id
    request = urllib.request.Request(
        url,
        data=body,
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


async def async_post_json(**kwargs: Any) -> tuple[int, dict[str, Any]]:
    return await asyncio.to_thread(post_json, **kwargs)


class OpenAIResponsesProvider:
    def __init__(self, *, api_key: str, model: str, base_url: str, timeout_seconds: int, max_output_tokens: int, auth_scheme: str = "bearer", project_id: str | None = None, request_params: dict[str, Any] | None = None, user_prefix: str = ""):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens
        self.auth_scheme = auth_scheme
        self.project_id = project_id
        self.request_params = request_params or {}
        self.user_prefix = user_prefix

    async def parse(
        self,
        *,
        system_prompt: str,
        user_text: str,
        schema: dict,
        response_mode: str,
    ) -> ProviderResult:
        payload: dict[str, Any] = {
            "model": self.model,
            "instructions": system_prompt,
            "input": user_text,
            "max_output_tokens": self.max_output_tokens,
            "temperature": 0,
        }
        if response_mode == "json_schema":
            payload["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": "shopping_list",
                    "schema": schema,
                    "strict": True,
                }
            }
        elif response_mode == "json_object":
            payload["text"] = {"format": {"type": "json_object"}}

        started = time.perf_counter()
        try:
            status, raw = await async_post_json(
                url=f"{self.base_url}/responses",
                api_key=self.api_key,
                payload=payload,
                timeout_seconds=self.timeout_seconds,
                auth_scheme=self.auth_scheme,
                project_id=self.project_id,
            )
            latency_ms = (time.perf_counter() - started) * 1000
            raw_text = _responses_output_text(raw)
            parsed_json = parse_json_text(raw_text)
            validation_error = _validation_error(parsed_json)
            return ProviderResult(
                provider="openai",
                model=self.model,
                raw_text=raw_text,
                parsed_json=parsed_json,
                usage=_usage_from_openai_responses(raw.get("usage") or {}),
                latency_ms=latency_ms,
                http_status=status,
                response_id=raw.get("id"),
                error_type="SCHEMA_VALIDATION_FAILURE" if validation_error else None,
                error_message=validation_error,
                attempt=1,
            )
        except Exception as exc:
            return _failure_result("openai", self.model, started, exc)


class ChatCompletionsProvider:
    def __init__(
        self,
        *,
        provider: str,
        api_key: str,
        model: str,
        base_url: str,
        timeout_seconds: int,
        max_output_tokens: int,
        auth_scheme: str = "bearer",
        project_id: str | None = None,
        request_params: dict[str, Any] | None = None,
        user_prefix: str = "",
    ):
        self.provider = provider
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens
        self.auth_scheme = auth_scheme
        self.project_id = project_id
        self.request_params = request_params or {}
        self.user_prefix = user_prefix

    async def parse(
        self,
        *,
        system_prompt: str,
        user_text: str,
        schema: dict,
        response_mode: str,
    ) -> ProviderResult:
        effective_system_prompt = system_prompt
        if response_mode in {"json_object", "text_json"}:
            effective_system_prompt = (
                f"{system_prompt}\n\n"
                "Формат ответа: корневой объект с ключом items. "
                "Каждый элемент items использует только поля: product, brand, quantity_value, quantity_unit, "
                "package_count, package_size_value, package_size_unit, attributes. "
                "Название продукта всегда пиши в поле product. Не используй поле name. "
                "Для отсутствующих значений используй null, для attributes используй массив."
            )
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": effective_system_prompt},
                {"role": "user", "content": f"{self.user_prefix}{user_text}"},
            ],
            "temperature": 0,
            "max_tokens": self.max_output_tokens,
        }
        payload.update(self.request_params)
        if response_mode == "json_schema":
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "shopping_list",
                    "strict": True,
                    "schema": schema,
                },
            }
        elif response_mode == "json_object":
            payload["response_format"] = {"type": "json_object"}

        started = time.perf_counter()
        try:
            status, raw = await async_post_json(
                url=f"{self.base_url}/chat/completions",
                api_key=self.api_key,
                payload=payload,
                timeout_seconds=self.timeout_seconds,
                auth_scheme=self.auth_scheme,
                project_id=self.project_id,
            )
            latency_ms = (time.perf_counter() - started) * 1000
            choice = (raw.get("choices") or [{}])[0]
            raw_text = ((choice.get("message") or {}).get("content") or "").strip()
            parsed_json = parse_json_text(raw_text)
            validation_error = _validation_error(parsed_json)
            return ProviderResult(
                provider=self.provider,
                model=self.model,
                raw_text=raw_text,
                parsed_json=parsed_json,
                usage=_usage_from_chat(raw.get("usage") or {}),
                latency_ms=latency_ms,
                http_status=status,
                response_id=raw.get("id"),
                error_type="SCHEMA_VALIDATION_FAILURE" if validation_error else None,
                error_message=validation_error,
                attempt=1,
            )
        except Exception as exc:
            return _failure_result(self.provider, self.model, started, exc)



def _validation_error(parsed_json: dict[str, Any] | None) -> str | None:
    try:
        ShoppingList.model_validate(parsed_json)
    except ValidationError as exc:
        return str(exc)
    return None

def _responses_output_text(raw: dict[str, Any]) -> str | None:
    parts: list[str] = []
    for item in raw.get("output") or []:
        for content in item.get("content") or []:
            if content.get("type") == "output_text" and content.get("text"):
                parts.append(content["text"])
    if parts:
        return "".join(parts).strip()
    return raw.get("output_text")


def _usage_from_openai_responses(usage: dict[str, Any]) -> Usage:
    input_details = usage.get("input_tokens_details") or {}
    output_details = usage.get("output_tokens_details") or {}
    return Usage(
        input_tokens=usage.get("input_tokens"),
        cached_input_tokens=input_details.get("cached_tokens"),
        output_tokens=usage.get("output_tokens"),
        reasoning_tokens=output_details.get("reasoning_tokens"),
        total_tokens=usage.get("total_tokens"),
    )


def _usage_from_chat(usage: dict[str, Any]) -> Usage:
    prompt_details = usage.get("prompt_tokens_details") or {}
    completion_details = usage.get("completion_tokens_details") or {}
    return Usage(
        input_tokens=usage.get("prompt_tokens"),
        cached_input_tokens=prompt_details.get("cached_tokens"),
        output_tokens=usage.get("completion_tokens"),
        reasoning_tokens=completion_details.get("reasoning_tokens"),
        total_tokens=usage.get("total_tokens"),
    )


def _failure_result(provider: str, model: str, started: float, exc: Exception) -> ProviderResult:
    status = exc.code if isinstance(exc, urllib.error.HTTPError) else None
    if isinstance(exc, TimeoutError):
        error_type = "TIMEOUT"
    elif isinstance(exc, urllib.error.HTTPError):
        error_type = "HTTP_4XX" if 400 <= exc.code < 500 else "HTTP_5XX"
        try:
            body = exc.read().decode("utf-8")[:1000]
            if body:
                exc = RuntimeError(f"HTTP {status}: {body}")
        except Exception:
            pass
    elif isinstance(exc, json.JSONDecodeError):
        error_type = "INVALID_JSON"
    elif isinstance(exc, ValidationError):
        error_type = "SCHEMA_VALIDATION_FAILURE"
    elif isinstance(exc, urllib.error.URLError):
        error_type = "NETWORK_ERROR"
    else:
        error_type = type(exc).__name__
    return ProviderResult(
        provider=provider,
        model=model,
        raw_text=None,
        parsed_json=None,
        usage=Usage(),
        latency_ms=(time.perf_counter() - started) * 1000,
        http_status=status,
        response_id=None,
        error_type=error_type,
        error_message=str(exc),
        attempt=1,
    )
