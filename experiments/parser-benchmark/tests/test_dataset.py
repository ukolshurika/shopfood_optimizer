from pathlib import Path

import pytest

from benchmark.dataset import dataset_sha256, load_jsonl


def test_load_dev_dataset():
    cases = load_jsonl(Path("data/dev.jsonl"))
    assert len(cases) >= 15
    assert cases[0].gold.items[0].product == "молоко"
    assert dataset_sha256(Path("data/dev.jsonl"))


def test_duplicate_ids_are_rejected(tmp_path):
    data = (
        '{"id":"dup","category":"x","input":"молоко","gold":{"items":[]}}\n'
        '{"id":"dup","category":"x","input":"хлеб","gold":{"items":[]}}\n'
    )
    path = tmp_path / "dup.jsonl"
    path.write_text(data, encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate case id"):
        load_jsonl(path)
