from __future__ import annotations

import json
import re
from typing import Any


def parse_json_text(text: str | None) -> dict[str, Any] | None:
    if not text:
        return None
    cleaned = text.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*(.*?)\s*```", cleaned, flags=re.DOTALL | re.IGNORECASE)
    if fenced:
        cleaned = fenced.group(1).strip()
    return json.loads(cleaned)
