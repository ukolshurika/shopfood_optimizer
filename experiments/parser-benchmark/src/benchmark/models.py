from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MeasureUnit = Literal["g", "kg", "ml", "l", "pcs"]


class ProductAttribute(BaseModel):
    key: str
    value: str


class ShoppingItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product: str
    brand: str | None = None
    quantity_value: float | None = None
    quantity_unit: MeasureUnit | None = None
    package_count: int | None = None
    package_size_value: float | None = None
    package_size_unit: MeasureUnit | None = None
    attributes: list[ProductAttribute] = Field(default_factory=list)


class ShoppingList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[ShoppingItem]


def shopping_list_schema() -> dict:
    return ShoppingList.model_json_schema()


def write_schema(path: Path) -> None:
    path.write_text(
        json.dumps(shopping_list_schema(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
