import json
from pathlib import Path

from benchmark.json_utils import normalize_prediction
from benchmark.models import shopping_list_schema


def test_checked_in_schema_matches_model():
    checked_in = json.loads(Path("schemas/shopping_list.schema.json").read_text(encoding="utf-8"))
    assert checked_in == shopping_list_schema()


def test_normalize_prediction_converts_attribute_shapes_without_mutating_input():
    value = {"items": [{"product": "молоко", "attributes": {"fat_percent": 3.2}}, {"product": "хлеб", "attributes": None}]}

    normalized = normalize_prediction(value)

    assert normalized["items"][0]["attributes"] == [{"key": "fat_percent", "value": "3.2"}]
    assert normalized["items"][1]["attributes"] == []
    assert value["items"][0]["attributes"] == {"fat_percent": 3.2}
