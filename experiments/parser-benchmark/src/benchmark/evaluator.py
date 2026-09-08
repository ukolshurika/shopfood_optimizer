from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from benchmark.canonicalize import canonical_item, canonical_list, norm_text
from benchmark.models import ShoppingList


@dataclass(frozen=True)
class CaseEvaluation:
    schema_valid: bool
    item_recall: float
    item_precision: float
    quantity_value_accuracy: float
    quantity_unit_accuracy: float
    package_semantics_accuracy: float
    whole_order_exact_match: bool
    critical_errors: list[str]
    matched_items: int
    gold_items: int
    predicted_items: int


def evaluate_case(
    *,
    gold: ShoppingList,
    prediction: dict[str, Any] | ShoppingList | None,
    evaluator_metadata: dict[str, Any] | None = None,
) -> CaseEvaluation:
    metadata = evaluator_metadata or {}
    if prediction is None:
        return _invalid_schema_result(len(gold.items), ["missing_prediction"])
    try:
        predicted_model = prediction if isinstance(prediction, ShoppingList) else ShoppingList.model_validate(prediction)
    except ValidationError:
        return _invalid_schema_result(len(gold.items), ["schema_validation_failure"])

    gold_items = canonical_list(gold)
    predicted_items = canonical_list(predicted_model)
    matches = _match_items(gold_items, predicted_items, metadata)

    matched_count = len(matches)
    recall = _safe_div(matched_count, len(gold_items))
    precision = _safe_div(matched_count, len(predicted_items))

    quantity_value_ok = 0
    quantity_unit_ok = 0
    package_ok = 0
    critical_errors: list[str] = []

    for gold_index, predicted_index in matches:
        gold_item = gold_items[gold_index]
        predicted_item = predicted_items[predicted_index]
        quantity_value_ok += gold_item["quantity_value"] == predicted_item["quantity_value"]
        quantity_unit_ok += gold_item["quantity_unit"] == predicted_item["quantity_unit"]
        package_fields_ok = (
            gold_item["package_count"] == predicted_item["package_count"]
            and gold_item["package_size_value"] == predicted_item["package_size_value"]
            and gold_item["package_size_unit"] == predicted_item["package_size_unit"]
        )
        package_ok += package_fields_ok

        if gold_item["quantity_value"] != predicted_item["quantity_value"]:
            critical_errors.append("wrong_quantity_value")
        if gold_item["quantity_unit"] != predicted_item["quantity_unit"]:
            critical_errors.append("wrong_quantity_unit")
        if not package_fields_ok:
            critical_errors.append("wrong_package_semantics")
        if gold_item["brand"] != predicted_item["brand"]:
            critical_errors.append("wrong_brand")
        if gold_item["attributes"] != predicted_item["attributes"]:
            critical_errors.append("wrong_attributes")

    missing = len(gold_items) - matched_count
    extra = len(predicted_items) - matched_count
    critical_errors.extend(["missing_item"] * missing)
    critical_errors.extend(["extra_item"] * extra)
    critical_errors.extend(_store_noise_errors(predicted_items))

    exact = (
        len(gold_items) == len(predicted_items)
        and matched_count == len(gold_items)
        and not critical_errors
    )

    return CaseEvaluation(
        schema_valid=True,
        item_recall=recall,
        item_precision=precision,
        quantity_value_accuracy=_safe_div(quantity_value_ok, matched_count),
        quantity_unit_accuracy=_safe_div(quantity_unit_ok, matched_count),
        package_semantics_accuracy=_safe_div(package_ok, matched_count),
        whole_order_exact_match=exact,
        critical_errors=critical_errors,
        matched_items=matched_count,
        gold_items=len(gold_items),
        predicted_items=len(predicted_items),
    )


def _invalid_schema_result(gold_count: int, errors: list[str]) -> CaseEvaluation:
    return CaseEvaluation(
        schema_valid=False,
        item_recall=0.0,
        item_precision=0.0,
        quantity_value_accuracy=0.0,
        quantity_unit_accuracy=0.0,
        package_semantics_accuracy=0.0,
        whole_order_exact_match=False,
        critical_errors=errors,
        matched_items=0,
        gold_items=gold_count,
        predicted_items=0,
    )


def _match_items(
    gold_items: list[dict[str, Any]],
    predicted_items: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> list[tuple[int, int]]:
    aliases_by_index = _aliases_by_gold_index(gold_items, metadata)
    used_predictions: set[int] = set()
    matches: list[tuple[int, int]] = []

    for gold_index, gold_item in enumerate(gold_items):
        accepted_names = aliases_by_index.get(gold_index, {gold_item["product"]})
        best_index = None
        best_score = -1
        for predicted_index, predicted_item in enumerate(predicted_items):
            if predicted_index in used_predictions:
                continue
            if predicted_item["product"] not in accepted_names:
                continue
            score = _similarity_score(gold_item, predicted_item)
            if score > best_score:
                best_score = score
                best_index = predicted_index
        if best_index is not None:
            used_predictions.add(best_index)
            matches.append((gold_index, best_index))
    return matches


def _aliases_by_gold_index(
    gold_items: list[dict[str, Any]],
    metadata: dict[str, Any],
) -> dict[int, set[str]]:
    result: dict[int, set[str]] = {}
    aliases = metadata.get("accepted_product_names", {})
    for index, item in enumerate(gold_items):
        accepted = {item["product"]}
        item_aliases = aliases.get(item["product"], []) if isinstance(aliases, dict) else []
        accepted.update(norm_text(alias) for alias in item_aliases)
        result[index] = {alias for alias in accepted if alias}
    return result


def _similarity_score(gold_item: dict[str, Any], predicted_item: dict[str, Any]) -> int:
    fields = [
        "brand",
        "quantity_value",
        "quantity_unit",
        "package_count",
        "package_size_value",
        "package_size_unit",
        "attributes",
    ]
    return sum(gold_item[field] == predicted_item[field] for field in fields)


def _store_noise_errors(items: list[dict[str, Any]]) -> list[str]:
    store_names = {"вкусвилл", "вв", "пятерочка", "магнит"}
    errors: list[str] = []
    for item in items:
        product = item["product"]
        if product in store_names:
            errors.append("store_name_as_product")
    return errors


def _safe_div(numerator: int | float, denominator: int | float) -> float:
    if denominator == 0:
        return 1.0
    return numerator / denominator


def evaluation_to_dict(evaluation: CaseEvaluation) -> dict[str, Any]:
    return {
        "schema_valid": evaluation.schema_valid,
        "item_recall": evaluation.item_recall,
        "item_precision": evaluation.item_precision,
        "quantity_value_accuracy": evaluation.quantity_value_accuracy,
        "quantity_unit_accuracy": evaluation.quantity_unit_accuracy,
        "package_semantics_accuracy": evaluation.package_semantics_accuracy,
        "whole_order_exact_match": evaluation.whole_order_exact_match,
        "critical_errors": evaluation.critical_errors,
        "matched_items": evaluation.matched_items,
        "gold_items": evaluation.gold_items,
        "predicted_items": evaluation.predicted_items,
    }
