from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from benchmark.models import ProductAttribute, ShoppingItem, ShoppingList

UNIT_ALIASES = {
    "гр": "g",
    "г": "g",
    "грамм": "g",
    "грамма": "g",
    "граммов": "g",
    "кг": "kg",
    "килограмм": "kg",
    "килограмма": "kg",
    "килограммов": "kg",
    "мл": "ml",
    "миллилитр": "ml",
    "миллилитра": "ml",
    "миллилитров": "ml",
    "л": "l",
    "литр": "l",
    "литра": "l",
    "литров": "l",
    "шт": "pcs",
    "штук": "pcs",
    "штуки": "pcs",
    "pcs": "pcs",
}


def norm_text(value: str | None) -> str | None:
    if value is None:
        return None
    return " ".join(value.strip().lower().replace("ё", "е").split())


def norm_unit(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = norm_text(value)
    return UNIT_ALIASES.get(normalized, normalized)


def norm_number(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value)).normalize()
    except (InvalidOperation, ValueError):
        return None


def canonical_attributes(attrs: list[ProductAttribute] | list[dict[str, Any]]) -> tuple[tuple[str, str], ...]:
    normalized = []
    for attr in attrs:
        key = attr.key if isinstance(attr, ProductAttribute) else attr["key"]
        value = attr.value if isinstance(attr, ProductAttribute) else attr["value"]
        normalized.append((norm_text(key) or "", norm_text(value) or ""))
    return tuple(sorted(normalized))


def canonical_item(item: ShoppingItem | dict[str, Any]) -> dict[str, Any]:
    if isinstance(item, dict):
        item = {
            **item,
            "quantity_unit": norm_unit(item.get("quantity_unit")),
            "package_size_unit": norm_unit(item.get("package_size_unit")),
        }
        item = ShoppingItem.model_validate(item)
    return {
        "product": norm_text(item.product),
        "brand": norm_text(item.brand),
        "quantity_value": norm_number(item.quantity_value),
        "quantity_unit": norm_unit(item.quantity_unit),
        "package_count": item.package_count,
        "package_size_value": norm_number(item.package_size_value),
        "package_size_unit": norm_unit(item.package_size_unit),
        "attributes": canonical_attributes(item.attributes),
    }


def canonical_list(value: ShoppingList | dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        value = ShoppingList.model_validate(value)
    return [canonical_item(item) for item in value.items]
