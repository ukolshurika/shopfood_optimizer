from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from benchmark.models import ShoppingList


@dataclass(frozen=True)
class DatasetCase:
    id: str
    category: str
    input: str
    gold: ShoppingList
    evaluator_metadata: dict[str, Any]


def load_jsonl(path: Path) -> list[DatasetCase]:
    cases: list[DatasetCase] = []
    seen_ids: set[str] = set()
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                raw = json.loads(line)
                case_id = raw["id"]
                if case_id in seen_ids:
                    raise ValueError(f"duplicate case id: {case_id}")
                seen_ids.add(case_id)
                cases.append(
                    DatasetCase(
                        id=case_id,
                        category=raw["category"],
                        input=raw["input"],
                        gold=ShoppingList.model_validate(raw["gold"]),
                        evaluator_metadata={
                            key: value
                            for key, value in raw.items()
                            if key not in {"id", "category", "input", "gold"}
                        },
                    )
                )
            except (KeyError, json.JSONDecodeError, ValidationError, ValueError) as exc:
                raise ValueError(f"{path}:{line_number}: invalid dataset row: {exc}") from exc
    return cases


def dataset_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
