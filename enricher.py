import sys
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import json
import random
import time
from datetime import datetime, timedelta
from pathlib import Path

NO_DATA_TTL_DAYS = 7  # 與 fetcher.NO_DATA_TTL_DAYS 保持一致


def _load_json(path: str) -> dict:
    p = Path(path)
    if p.exists():
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_json(path: str, data: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class LookupEnricher:
    def __init__(self, lookup_file: str, cache_file: str):
        self.lookup_file = lookup_file
        self.cache_file = cache_file
        self.lookup: dict = _load_json(lookup_file)
        self.cache: dict = _load_json(cache_file)

    def _save_lookup(self) -> None:
        _save_json(self.lookup_file, self.lookup)

    def merge_dict(self, data: dict) -> int:
        count = 0
        for code, entry in data.items():
            if code not in self.lookup:
                self.lookup[code] = {
                    "title": entry.get("title", ""),
                    "actresses": entry.get("actresses", []),
                }
                count += 1
        self._save_lookup()
        return count

    def scrape_new_releases(self, fetcher, stop_after_known: int = 50,
                            max_pages: int = 10, progress_cb=None) -> int:
        raise NotImplementedError

    def retry_no_data(self, fetcher, progress_cb=None) -> int:
        raise NotImplementedError

    def scrape_listing_pages(self, fetcher, start_page: int = 1,
                             max_pages: int = 100, progress_cb=None) -> tuple[int, int]:
        raise NotImplementedError

    def _fetch_listing_page(self, fetcher, page_num: int) -> list[tuple[str, str]]:
        raise NotImplementedError
