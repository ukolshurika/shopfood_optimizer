from __future__ import annotations

import asyncio
import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from typing import Any

from pydantic import ValidationError

from benchmark.json_utils import parse_json_text
from benchmark.models import ShoppingList
from benchmark.pricing import Usage
from benchmark.providers.base import ProviderResult


class GigaChatProvider:
    def __init__(
        self,
        *,
        credentials: str,
        scope: str,
        model: str,
        base_url: str,
        oauth_url: str,
        timeout_seconds: int,
        max_output_tokens: int,
        verify_ssl: bool = True,
    ):
        self.credentials = credentials
        self.scope = scope
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.oauth_url = oauth_url
        self.timeout_seconds = timeout_seconds
        self.max_output_tokens = max_output_tokens
        self.verify_ssl = verify_ssl
        self._access_token: str | None = None
        self._expires_at_ms: int = 0

    async def parse(
        self,
        *,
        system_prompt: str,
        user_text: str,
        schema: dict,
        response_mode: str,
    ) -> ProviderResult:
        started = time.perf_counter()
        try:
            token = await self._access_token_value()
            payload: dict[str, Any] = {
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_text},
                ],
                "temperature": 0,
                "max_tokens": self.max_output_tokens,
            }
            if response_mode == "json_schema":
                payload["response_format"] = {
                    "type": "json_schema",
                    "schema": schema,
                    "strict": True,
                }
            elif response_mode == "json_object":
                payload["response_format"] = {"type": "json_schema", "schema": schema, "strict": True}

            status, raw = await asyncio.to_thread(
                self._post_json,
                f"{self.base_url}/chat/completions",
                payload,
                {"Authorization": f"Bearer {token}", "Content-Type": "application/json", "Accept": "application/json"},
            )
            latency_ms = (time.perf_counter() - started) * 1000
            choice = (raw.get("choices") or [{}])[0]
            raw_text = ((choice.get("message") or {}).get("content") or "").strip()
            parsed_json = parse_json_text(raw_text)
            ShoppingList.model_validate(parsed_json)
            return ProviderResult(
                provider="gigachat_freemium",
                model=self.model,
                raw_text=raw_text,
                parsed_json=parsed_json,
                usage=_usage_from_gigachat(raw.get("usage") or {}),
                latency_ms=latency_ms,
                http_status=status,
                response_id=raw.get("id"),
                error_type=None,
                error_message=None,
                attempt=1,
            )
        except Exception as exc:
            return _failure_result("gigachat_freemium", self.model, started, exc)

    async def _access_token_value(self) -> str:
        now_ms = int(time.time() * 1000)
        if self._access_token and now_ms < self._expires_at_ms - 60_000:
            return self._access_token
        status, raw = await asyncio.to_thread(self._request_token)
        if status != 200 or not raw.get("access_token"):
            raise RuntimeError("GigaChat OAuth did not return access_token")
        self._access_token = raw["access_token"]
        self._expires_at_ms = int(raw.get("expires_at") or 0)
        return self._access_token

    def _request_token(self) -> tuple[int, dict[str, Any]]:
        body = urllib.parse.urlencode({"scope": self.scope}).encode("utf-8")
        request = urllib.request.Request(
            self.oauth_url,
            data=body,
            headers={
                "Authorization": f"Basic {self.credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "RqUID": str(uuid.uuid4()),
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds, context=self._ssl_context()) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def _post_json(self, url: str, payload: dict[str, Any], headers: dict[str, str]) -> tuple[int, dict[str, Any]]:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds, context=self._ssl_context()) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def _ssl_context(self):
        if self.verify_ssl:
            return None
        return ssl._create_unverified_context()


def _usage_from_gigachat(usage: dict[str, Any]) -> Usage:
    return Usage(
        input_tokens=usage.get("prompt_tokens") or usage.get("input_tokens"),
        cached_input_tokens=usage.get("precached_prompt_tokens"),
        output_tokens=usage.get("completion_tokens") or usage.get("output_tokens"),
        reasoning_tokens=None,
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
