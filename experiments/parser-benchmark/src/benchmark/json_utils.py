from __future__ import annotations

import json
import re
from copy import deepcopy
from typing import Any


def parse_json_text(text: str | None) -> dict[str, Any] | None:
    if not text:
        return None
    cleaned = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        cleaned = fenced.group(1).strip()
    return json.loads(cleaned)


def normalize_prediction(value: dict[str, Any] | None) -> dict[str, Any] | None:
    """Normalize harmless shape drift without changing the original raw text."""
    if not isinstance(value, dict):
        return value
    normalized = deepcopy(value)
    for item in normalized.get("items") or []:
        if not isinstance(item, dict):
            continue
        attributes = item.get("attributes")
        if attributes is None:
            item["attributes"] = []
        elif isinstance(attributes, dict):
            item["attributes"] = [
                {"key": str(key), "value": str(attribute_value)}
                for key, attribute_value in attributes.items()
                if attribute_value is not None
            ]
    return normalized
