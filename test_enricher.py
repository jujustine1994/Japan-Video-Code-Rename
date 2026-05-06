import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta

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


def test_scrape_new_releases_adds_new_entries(tmp_files):
    lookup_file, cache_file = tmp_files
    enricher = LookupEnricher(lookup_file, cache_file)
    mock_fetcher = MagicMock()

    call_count = [0]
    def mock_fetch(fetcher, page_num):
        call_count[0] += 1
        if page_num == 1:
            return [("NEW-001", "新作1"), ("NEW-002", "新作2")]
        return []

    enricher._fetch_listing_page = mock_fetch

    with patch("time.sleep"):
        result = enricher.scrape_new_releases(mock_fetcher, stop_after_known=50, max_pages=5)

    assert result == 2
    assert "NEW-001" in enricher.lookup
    assert enricher.lookup["NEW-001"]["partial"] is True
    assert enricher.lookup["NEW-002"]["partial"] is True


def test_scrape_new_releases_stops_on_consecutive_known(tmp_files):
    lookup_file, cache_file = tmp_files
    known = {f"KNOWN-{i:03d}": {"title": f"t{i}", "actresses": []} for i in range(60)}
    Path(lookup_file).write_text(json.dumps(known), encoding="utf-8")

    enricher = LookupEnricher(lookup_file, cache_file)
    mock_fetcher = MagicMock()
    page_calls = [0]

    def mock_fetch(fetcher, page_num):
        page_calls[0] += 1
        return [(f"KNOWN-{i:03d}", f"t{i}") for i in range(24)]

    enricher._fetch_listing_page = mock_fetch

    with patch("time.sleep"):
        result = enricher.scrape_new_releases(mock_fetcher, stop_after_known=50, max_pages=20)

    assert result == 0
    assert page_calls[0] <= 4  # 應在 50 筆連續已知後停止


def test_scrape_new_releases_respects_max_pages(tmp_files):
    lookup_file, cache_file = tmp_files
    enricher = LookupEnricher(lookup_file, cache_file)
    mock_fetcher = MagicMock()

    page_calls = [0]
    def mock_fetch(fetcher, page_num):
        page_calls[0] += 1
        return [(f"NEW-{page_num:02d}-{i:02d}", f"title") for i in range(5)]

    enricher._fetch_listing_page = mock_fetch

    with patch("time.sleep"):
        enricher.scrape_new_releases(mock_fetcher, stop_after_known=9999, max_pages=3)

    assert page_calls[0] == 3
