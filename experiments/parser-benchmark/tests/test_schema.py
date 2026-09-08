import json
from pathlib import Path

from benchmark.models import shopping_list_schema


def test_checked_in_schema_matches_model():
    checked_in = json.loads(Path("schemas/shopping_list.schema.json").read_text(encoding="utf-8"))
    assert checked_in == shopping_list_schema()
