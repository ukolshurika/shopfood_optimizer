from benchmark.evaluator import evaluate_case
from benchmark.models import ShoppingList


def shopping_list(items):
    return ShoppingList.model_validate({"items": items})


def test_exact_match_ignores_item_order():
    gold = shopping_list(
        [
            {"product": "молоко", "quantity_value": 2, "quantity_unit": "l"},
            {"product": "банан", "quantity_value": 1, "quantity_unit": "kg"},
        ]
    )
    prediction = {
        "items": [
            {"product": "банан", "quantity_value": 1, "quantity_unit": "kg"},
            {"product": "молоко", "quantity_value": 2, "quantity_unit": "l"},
        ]
    }
    result = evaluate_case(gold=gold, prediction=prediction)
    assert result.whole_order_exact_match is True
    assert result.critical_errors == []


def test_alias_matching():
    gold = shopping_list([{"product": "куриная грудка"}])
    prediction = {"items": [{"product": "грудка курицы"}]}
    result = evaluate_case(
        gold=gold,
        prediction=prediction,
        evaluator_metadata={"accepted_product_names": {"куриная грудка": ["грудка курицы"]}},
    )
    assert result.item_recall == 1.0
    assert result.whole_order_exact_match is True


def test_package_semantics_error_is_critical():
    gold = shopping_list([{"product": "молоко", "package_count": 2}])
    prediction = {"items": [{"product": "молоко", "quantity_value": 2, "quantity_unit": "l"}]}
    result = evaluate_case(gold=gold, prediction=prediction)
    assert "wrong_package_semantics" in result.critical_errors
    assert "wrong_quantity_unit" in result.critical_errors


def test_store_name_as_product_is_critical():
    gold = shopping_list([{"product": "молоко"}])
    prediction = {"items": [{"product": "молоко"}, {"product": "магнит"}]}
    result = evaluate_case(gold=gold, prediction=prediction)
    assert "store_name_as_product" in result.critical_errors
    assert result.item_precision == 0.5


def test_invalid_schema():
    gold = shopping_list([{"product": "молоко"}])
    result = evaluate_case(gold=gold, prediction={"items": [{"product": "молоко", "quantity_unit": "liters"}]})
    assert result.schema_valid is False
    assert "schema_validation_failure" in result.critical_errors
