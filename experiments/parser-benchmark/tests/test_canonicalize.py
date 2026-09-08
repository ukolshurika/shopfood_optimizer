from benchmark.canonicalize import canonical_item, norm_text, norm_unit


def test_text_normalization():
    assert norm_text("  Молоко  Ёлка  ") == "молоко елка"


def test_unit_aliases():
    assert norm_unit("гр") == "g"
    assert norm_unit("литра") == "l"
    assert norm_unit("штук") == "pcs"


def test_canonical_item_sorts_attributes_and_normalizes_numbers():
    item = canonical_item(
        {
            "product": "Творог",
            "brand": None,
            "quantity_value": 1.0,
            "quantity_unit": "кг",
            "package_count": None,
            "package_size_value": None,
            "package_size_unit": None,
            "attributes": [
                {"key": "type", "value": "Обычное"},
                {"key": "fat_percent", "value": "5"},
            ],
        }
    )
    assert item["product"] == "творог"
    assert str(item["quantity_value"]) == "1"
    assert item["quantity_unit"] == "kg"
    assert item["attributes"] == (("fat_percent", "5"), ("type", "обычное"))
