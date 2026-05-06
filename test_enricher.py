import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import json
import pytest
from pathlib import Path

from enricher import LookupEnricher


@pytest.fixture
def tmp_files(tmp_path):
    lookup = tmp_path / "lookup.json"
    cache = tmp_path / "cache.json"
    lookup.write_text("{}", encoding="utf-8")
    cache.write_text("{}", encoding="utf-8")
    return str(lookup), str(cache)


def test_merge_dict_adds_new_entries(tmp_files):
    lookup_file, cache_file = tmp_files
    enricher = LookupEnricher(lookup_file, cache_file)
    data = {
        "ABC-001": {"title": "テスト", "actresses": ["山田花子"]},
        "ABC-002": {"title": "テスト2", "actresses": []},
    }
    count = enricher.merge_dict(data)
    assert count == 2
    assert enricher.lookup["ABC-001"] == {"title": "テスト", "actresses": ["山田花子"]}
    assert enricher.lookup["ABC-002"] == {"title": "テスト2", "actresses": []}


def test_merge_dict_skips_existing(tmp_files):
    lookup_file, cache_file = tmp_files
    Path(lookup_file).write_text(
        json.dumps({"ABC-001": {"title": "既存", "actresses": ["既存女優"]}}),
        encoding="utf-8"
    )
    enricher = LookupEnricher(lookup_file, cache_file)
    count = enricher.merge_dict({"ABC-001": {"title": "上書き", "actresses": []}})
    assert count == 0
    assert enricher.lookup["ABC-001"]["title"] == "既存"


def test_merge_dict_persists_to_file(tmp_files):
    lookup_file, cache_file = tmp_files
    enricher = LookupEnricher(lookup_file, cache_file)
    enricher.merge_dict({"XYZ-001": {"title": "保存テスト", "actresses": []}})
    saved = json.loads(Path(lookup_file).read_text(encoding="utf-8"))
    assert "XYZ-001" in saved
